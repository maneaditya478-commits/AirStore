import uuid
import threading
import logging
from typing import Dict, Any, List
import httpx
from datetime import datetime, timezone

from airstore.core.config import settings
from airstore.core.models import (
    NodeStatus, ReplicaStatus, FileStatus, ChunkReplicaModel, EventModel, EventType
)
from airstore.manager.database.db import DatabaseManager
from airstore.manager.placement import PlacementStrategy, RuleBasedPlacementStrategy, PlacementError

logger = logging.getLogger("airstore.manager.recovery")

class RecoveryService:
    """
    Orchestrates fault detection, multi-node recovery, returning node reconciliation,
    and replica consistency auditing.
    """

    def __init__(
        self,
        db: DatabaseManager,
        placement_strategy: PlacementStrategy = None
    ):
        self.db = db
        self.placement = placement_strategy or RuleBasedPlacementStrategy()
        self._lock = threading.Lock()

    def reconcile_returning_node(self, node_id: str) -> Dict[str, Any]:
        """Reconcile missing replicas when a node comes back ONLINE."""
        with self._lock:
            missing_replicas = [r for r in self.db.get_replicas_for_node(node_id) if r.status == ReplicaStatus.MISSING]
            reconciled = 0
            node = self.db.get_node(node_id)
            if not node:
                return {"reconciled": 0}

            for rep in missing_replicas:
                # Query node verify endpoint
                verify_url = f"http://{node.ip}:{node.port}/chunks/{rep.chunk_id}/verify"
                try:
                    with self.db.get_connection() as conn:
                        chunk_row = conn.execute("SELECT sha256 FROM chunks WHERE chunk_id = ?;", (rep.chunk_id,)).fetchone()
                    if chunk_row:
                        with httpx.Client(timeout=3.0) as client:
                            resp = client.get(verify_url, params={"sha256": chunk_row["sha256"]})
                            if resp.status_code == 200 and resp.json().get("valid") is True:
                                self.db.update_replica_status(rep.chunk_id, node_id, ReplicaStatus.STORED)
                                reconciled += 1
                except Exception:
                    pass

            if reconciled > 0:
                logger.info(f"Node {node_id} returned online. Reconciled {reconciled} existing verified chunk replicas.")
            return {"node_id": node_id, "reconciled": reconciled}

    def audit_replica_consistency(self) -> Dict[str, Any]:
        """Audit cluster-wide replica health and consistency status."""
        files = self.db.list_files()
        nodes = {n.node_id: n for n in self.db.list_nodes()}

        total_files = len(files)
        total_chunks = 0
        total_replicas = 0
        stored_replicas = 0
        missing_replicas = 0
        corrupted_replicas = 0
        inconsistent_files = []

        for f in files:
            chunks = self.db.get_chunks_for_file(f.file_id)
            total_chunks += len(chunks)
            file_inconsistent = False

            for c in chunks:
                reps = self.db.get_replicas_for_chunk(c.chunk_id)
                total_replicas += len(reps)

                stored = 0
                for r in reps:
                    if r.status == ReplicaStatus.STORED:
                        stored += 1
                        stored_replicas += 1
                    elif r.status == ReplicaStatus.MISSING:
                        missing_replicas += 1
                    elif r.status == ReplicaStatus.CORRUPTED:
                        corrupted_replicas += 1

                if stored < f.replication_factor:
                    file_inconsistent = True

            if file_inconsistent:
                inconsistent_files.append(f.file_id)

        return {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "total_replicas": total_replicas,
            "stored_replicas": stored_replicas,
            "missing_replicas": missing_replicas,
            "corrupted_replicas": corrupted_replicas,
            "inconsistent_files_count": len(inconsistent_files),
            "healthy": len(inconsistent_files) == 0
        }

    def recover_node_failure(self, failed_node_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._execute_node_recovery(failed_node_id)

    def _execute_node_recovery(self, failed_node_id: str) -> Dict[str, Any]:
        """
        Process failure of a node:
        1. Identify affected chunk replicas.
        2. Mark failed node replicas as MISSING.
        3. Re-replicate chunks to healthy replacement nodes.
        """
        logger.warning(f"Initiating recovery process for failed node: {failed_node_id}")

        # Mark node as OFFLINE
        self.db.update_node_status(failed_node_id, NodeStatus.OFFLINE)

        # Log node offline event
        event_off = EventModel(
            event_id=str(uuid.uuid4()),
            event_type=EventType.NODE_OFFLINE,
            message=f"Node '{failed_node_id}' detected OFFLINE.",
            details={"node_id": failed_node_id}
        )
        self.db.add_event(event_off)

        # Log recovery start event
        event_rec_start = EventModel(
            event_id=str(uuid.uuid4()),
            event_type=EventType.RECOVERY_STARTED,
            message=f"Auto-recovery process started for node '{failed_node_id}'.",
            details={"node_id": failed_node_id}
        )
        self.db.add_event(event_rec_start)

        # Get all chunk replicas on failed node
        affected_replicas = self.db.get_replicas_for_node(failed_node_id)
        if not affected_replicas:
            logger.info(f"No active chunk replicas were hosted on failed node {failed_node_id}.")
            return {"status": "COMPLETED", "recovered_chunks": 0, "failed_chunks": 0}

        # Mark affected replicas on failed node as MISSING
        for rep in affected_replicas:
            self.db.update_replica_status(rep.chunk_id, failed_node_id, ReplicaStatus.MISSING)

        online_nodes = [n for n in self.db.list_nodes() if n.status == NodeStatus.ONLINE]
        node_map = {n.node_id: n for n in self.db.list_nodes()}

        recovered_count = 0
        failed_count = 0

        for rep in affected_replicas:
            chunk_id = rep.chunk_id
            
            # Find surviving replicas
            all_chunk_replicas = self.db.get_replicas_for_chunk(chunk_id)
            surviving_replicas = [
                r for r in all_chunk_replicas
                if r.status == ReplicaStatus.STORED
                and r.node_id in node_map
                and node_map[r.node_id].status == NodeStatus.ONLINE
            ]

            if not surviving_replicas:
                logger.error(f"CRITICAL: No surviving replicas available for chunk {chunk_id}!")
                failed_count += 1
                # Mark file corrupted
                with self.db.get_connection() as conn:
                    row = conn.execute("SELECT file_id FROM chunks WHERE chunk_id = ?;", (chunk_id,)).fetchone()
                    if row:
                        self.db.update_file_status(row["file_id"], FileStatus.CORRUPTED)
                continue

            # Pick source node from surviving replicas
            source_node = node_map[surviving_replicas[0].node_id]
            source_url = f"http://{source_node.ip}:{source_node.port}"

            # Existing replica node IDs to exclude
            existing_node_ids = [r.node_id for r in all_chunk_replicas if r.status != ReplicaStatus.MISSING]

            try:
                # Get chunk info
                with self.db.get_connection() as conn:
                    chunk_row = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?;", (chunk_id,)).fetchone()
                
                if not chunk_row:
                    continue

                from airstore.core.models import ChunkModel
                chunk_model = ChunkModel(
                    chunk_id=chunk_row["chunk_id"],
                    file_id=chunk_row["file_id"],
                    sequence_number=chunk_row["sequence_number"],
                    size=chunk_row["size"],
                    sha256=chunk_row["sha256"]
                )

                # Select replacement node
                target_nodes = self.placement.select_nodes_for_chunk(
                    chunk=chunk_model,
                    available_nodes=online_nodes,
                    replication_factor=1,
                    existing_replica_node_ids=existing_node_ids
                )

                if not target_nodes:
                    raise PlacementError(f"No available replacement node for chunk {chunk_id}")

                target_node = target_nodes[0]
                target_url = f"http://{target_node.ip}:{target_node.port}/replicate"

                # Instruct target node to replicate chunk from source node
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(target_url, json={
                        "chunk_id": chunk_id,
                        "source_node_url": source_url,
                        "sha256": chunk_model.sha256
                    })
                    resp.raise_for_status()

                # Record new replica in database
                max_rep_num = max([r.replica_number for r in all_chunk_replicas], default=0)
                new_replica = ChunkReplicaModel(
                    chunk_id=chunk_id,
                    node_id=target_node.node_id,
                    replica_number=max_rep_num + 1,
                    status=ReplicaStatus.STORED
                )
                self.db.add_replica(new_replica)
                recovered_count += 1

                logger.info(f"Chunk {chunk_id} successfully re-replicated from node {source_node.node_id} to node {target_node.node_id}")

            except Exception as e:
                logger.error(f"Failed to recover replica for chunk {chunk_id}: {e}")
                failed_count += 1

        rec_status = "COMPLETED" if failed_count == 0 else "PARTIAL_FAILURE"
        event_rec_end = EventModel(
            event_id=str(uuid.uuid4()),
            event_type=EventType.RECOVERY_COMPLETED if failed_count == 0 else EventType.RECOVERY_FAILED,
            message=f"Recovery finished for node '{failed_node_id}'. Recovered: {recovered_count}, Failed: {failed_count}.",
            details={"failed_node_id": failed_node_id, "recovered": recovered_count, "failed": failed_count}
        )
        self.db.add_event(event_rec_end)

        return {
            "status": rec_status,
            "failed_node_id": failed_node_id,
            "recovered_chunks": recovered_count,
            "failed_chunks": failed_count
        }
