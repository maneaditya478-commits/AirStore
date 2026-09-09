import uuid
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Generator, Optional, Union
import httpx
from datetime import datetime, timezone

from airstore.core.config import settings
from airstore.core.models import (
    FileModel, ChunkModel, ChunkReplicaModel, NodeModel, TransferModel, EventModel,
    FileStatus, ReplicaStatus, TransferType, TransferStatus, EventType, NodeStatus
)
from airstore.core.chunking import FileChunker, IntegrityError
from airstore.core.encryption import ChunkEncryptor
from airstore.core.hashing import calculate_bytes_hash
from airstore.manager.database.db import DatabaseManager
from airstore.manager.placement import PlacementStrategy, RuleBasedPlacementStrategy, InsufficientNodesError

logger = logging.getLogger("airstore.manager.storage_manager")

class StorageManagerService:
    """
    Core manager service handling file distribution, replica tracking, and streaming reconstruction.
    """

    def __init__(
        self,
        db: DatabaseManager,
        placement_strategy: Optional[PlacementStrategy] = None
    ):
        self.db = db
        self.placement = placement_strategy or RuleBasedPlacementStrategy()

    def process_file_upload(
        self,
        source_file_path: Union[str, Path],
        filename: Optional[str] = None,
        chunk_size: int = settings.CHUNK_SIZE,
        replication_factor: int = settings.REPLICATION_FACTOR,
        encrypted: bool = settings.ENCRYPTION_ENABLED
    ) -> FileModel:
        path = Path(source_file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Upload source file does not exist: {path}")

        file_id = str(uuid.uuid4())
        fname = filename or path.name
        transfer_id = str(uuid.uuid4())

        # Create initial transfer record
        transfer = TransferModel(
            transfer_id=transfer_id,
            file_id=file_id,
            transfer_type=TransferType.UPLOAD,
            status=TransferStatus.IN_PROGRESS,
            progress=0.0
        )
        self.db.create_transfer(transfer)

        try:
            # 1. Chunk and get file info
            logger.info(f"Chunking upload file {fname} (ID: {file_id})...")
            overall_hash, file_size, chunk_models = FileChunker.get_file_info_and_chunks(
                path, file_id=file_id, chunk_size=chunk_size
            )

            # Create File record
            file_model = FileModel(
                file_id=file_id,
                filename=fname,
                size=file_size,
                overall_hash=overall_hash,
                status=FileStatus.UPLOADING,
                chunk_size=chunk_size,
                replication_factor=replication_factor,
                encrypted=encrypted
            )
            self.db.create_file(file_model)
            self.db.create_chunks(chunk_models)

            # Check available nodes
            active_nodes = [n for n in self.db.list_nodes() if n.status == NodeStatus.ONLINE]
            if not active_nodes:
                raise InsufficientNodesError("No ONLINE storage nodes are currently registered with Manager.")

            encryptor = ChunkEncryptor(settings.encryption_key) if encrypted else None

            # Stream & upload chunks
            start_time = time.time()
            total_chunks = len(chunk_models)
            
            with httpx.Client(timeout=30.0) as client:
                for index, (chunk_info, chunk_bytes) in enumerate(FileChunker.stream_chunks(path, file_id=file_id, chunk_size=chunk_size)):
                    # Decides nodes for this chunk's replicas
                    target_nodes = self.placement.select_nodes_for_chunk(
                        chunk_info, active_nodes, replication_factor
                    )

                    # Prepare payload (encrypt if configured)
                    payload_data = encryptor.encrypt_chunk(chunk_bytes) if encryptor else chunk_bytes

                    replica_num = 1
                    for node in target_nodes:
                        already_exists = False
                        if not encrypted:
                            node_verify_url = f"http://{node.ip}:{node.port}/chunks/{chunk_info.chunk_id}/verify"
                            try:
                                v_resp = client.get(node_verify_url, params={"sha256": chunk_info.sha256})
                                if v_resp.status_code == 200 and v_resp.json().get("valid") is True:
                                    already_exists = True
                                    logger.info(f"Resumable upload: Chunk {chunk_info.chunk_id} verified on node {node.node_id}. Skipping retransmission.")
                            except Exception:
                                already_exists = False

                        if not already_exists:
                            node_url = f"http://{node.ip}:{node.port}/chunks/{chunk_info.chunk_id}"
                            resp = client.put(node_url, content=payload_data, params={"sha256": chunk_info.sha256 if not encrypted else None})
                            resp.raise_for_status()

                        # Save replica metadata
                        replica = ChunkReplicaModel(
                            chunk_id=chunk_info.chunk_id,
                            node_id=node.node_id,
                            replica_number=replica_num,
                            status=ReplicaStatus.STORED
                        )
                        self.db.add_replica(replica)
                        replica_num += 1

                # Update transfer progress
                progress = round(((index + 1) / total_chunks) * 100.0, 2)
                elapsed = max(time.time() - start_time, 0.001)
                speed_mbps = round(((index + 1) * chunk_size / (1024 * 1024)) / elapsed, 2)
                self.db.update_transfer(transfer_id, progress=progress, speed_mbps=speed_mbps)

            # Upload complete
            self.db.update_file_status(file_id, FileStatus.ACTIVE)
            self.db.update_transfer(
                transfer_id, progress=100.0, status=TransferStatus.COMPLETED
            )

            # Log event
            event = EventModel(
                event_id=str(uuid.uuid4()),
                event_type=EventType.FILE_UPLOADED,
                message=f"File '{fname}' ({file_size} bytes, {total_chunks} chunks) uploaded successfully.",
                details={"file_id": file_id, "filename": fname, "size": file_size, "chunks": total_chunks}
            )
            self.db.add_event(event)
            logger.info(f"File '{fname}' successfully uploaded to {len(active_nodes)} nodes.")
            return self.db.get_file(file_id)

        except Exception as e:
            logger.error(f"File upload failed for {fname}: {e}")
            self.db.update_file_status(file_id, FileStatus.CORRUPTED)
            self.db.update_transfer(
                transfer_id, progress=0.0, status=TransferStatus.FAILED, error_message=str(e)
            )
            raise e

    def stream_file_reconstruction(
        self,
        file_id: str,
        output_path: Union[str, Path]
    ) -> bool:
        file_model = self.db.get_file(file_id)
        if not file_model:
            raise FileNotFoundError(f"File ID {file_id} not found in metadata database.")

        transfer_id = str(uuid.uuid4())
        transfer = TransferModel(
            transfer_id=transfer_id,
            file_id=file_id,
            transfer_type=TransferType.DOWNLOAD,
            status=TransferStatus.IN_PROGRESS,
            progress=0.0
        )
        self.db.create_transfer(transfer)

        chunks = self.db.get_chunks_for_file(file_id)
        total_chunks = len(chunks)
        encryptor = ChunkEncryptor(settings.encryption_key) if file_model.encrypted else None
        node_map = {n.node_id: n for n in self.db.list_nodes()}

        def chunk_stream_generator():
            start_time = time.time()
            for idx, chunk in enumerate(chunks):
                replicas = self.db.get_replicas_for_chunk(chunk.chunk_id)
                stored_replicas = [r for r in replicas if r.status == ReplicaStatus.STORED]

                retrieved_data = None
                successful_node_id = None

                for replica in stored_replicas:
                    node = node_map.get(replica.node_id)
                    if not node or node.status != NodeStatus.ONLINE:
                        continue

                    node_url = f"http://{node.ip}:{node.port}/chunks/{chunk.chunk_id}"
                    try:
                        with httpx.Client(timeout=30.0) as client:
                            resp = client.get(node_url)
                            if resp.status_code == 200:
                                raw_bytes = resp.content
                                # Decrypt if encrypted
                                plaintext = encryptor.decrypt_chunk(raw_bytes) if encryptor else raw_bytes
                                # Verify chunk hash
                                if calculate_bytes_hash(plaintext) == chunk.sha256:
                                    retrieved_data = plaintext
                                    successful_node_id = node.node_id
                                    break
                                else:
                                    logger.warning(f"Chunk {chunk.chunk_id} from node {node.node_id} failed hash check!")
                                    self.db.update_replica_status(chunk.chunk_id, node.node_id, ReplicaStatus.CORRUPTED)
                    except Exception as err:
                        logger.warning(f"Failed to retrieve chunk {chunk.chunk_id} from node {node.node_id}: {err}")

                if retrieved_data is None:
                    raise IntegrityError(
                        f"Failed to retrieve healthy chunk {chunk.chunk_id} (seq {chunk.sequence_number}) from any available node."
                    )

                progress = round(((idx + 1) / total_chunks) * 100.0, 2)
                elapsed = max(time.time() - start_time, 0.001)
                speed_mbps = round(((idx + 1) * chunk.size / (1024 * 1024)) / elapsed, 2)
                self.db.update_transfer(transfer_id, progress=progress, speed_mbps=speed_mbps)

                yield retrieved_data

        try:
            success = FileChunker.assemble_file_from_stream(
                chunk_stream_generator(),
                output_path=output_path,
                expected_overall_hash=file_model.overall_hash
            )
            self.db.update_transfer(transfer_id, progress=100.0, status=TransferStatus.COMPLETED)
            
            event = EventModel(
                event_id=str(uuid.uuid4()),
                event_type=EventType.FILE_DOWNLOADED,
                message=f"File '{file_model.filename}' successfully reconstructed and verified.",
                details={"file_id": file_id, "filename": file_model.filename}
            )
            self.db.add_event(event)
            return success
        except Exception as e:
            self.db.update_transfer(transfer_id, progress=0.0, status=TransferStatus.FAILED, error_message=str(e))
            raise e

    def delete_file(self, file_id: str) -> bool:
        file_model = self.db.get_file(file_id)
        if not file_model:
            return False

        chunks = self.db.get_chunks_for_file(file_id)
        node_map = {n.node_id: n for n in self.db.list_nodes()}

        for chunk in chunks:
            replicas = self.db.get_replicas_for_chunk(chunk.chunk_id)
            for replica in replicas:
                node = node_map.get(replica.node_id)
                if node and node.status == NodeStatus.ONLINE:
                    url = f"http://{node.ip}:{node.port}/chunks/{chunk.chunk_id}"
                    try:
                        with httpx.Client(timeout=5.0) as client:
                            client.delete(url)
                    except Exception:
                        pass

        self.db.delete_file(file_id)
        event = EventModel(
            event_id=str(uuid.uuid4()),
            event_type=EventType.FILE_DELETED,
            message=f"File '{file_model.filename}' and its chunks deleted.",
            details={"file_id": file_id}
        )
        self.db.add_event(event)
        return True
