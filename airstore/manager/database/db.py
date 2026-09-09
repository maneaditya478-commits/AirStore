import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from airstore.core.models import (
    NodeModel, FileModel, ChunkModel, ChunkReplicaModel, TransferModel, EventModel,
    NodeStatus, FileStatus, ReplicaStatus, TransferType, TransferStatus, EventType
)

logger = logging.getLogger("airstore.manager.db")

class DatabaseManager:
    """SQLite Database Manager for AirStore Controller."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self):
        """Create tables if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                total_storage INTEGER NOT NULL,
                available_storage INTEGER NOT NULL,
                status TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                overall_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                replication_factor INTEGER NOT NULL,
                encrypted INTEGER NOT NULL DEFAULT 0
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files (file_id) ON DELETE CASCADE
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk_replicas (
                chunk_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                replica_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, node_id),
                FOREIGN KEY (chunk_id) REFERENCES chunks (chunk_id) ON DELETE CASCADE,
                FOREIGN KEY (node_id) REFERENCES nodes (node_id) ON DELETE CASCADE
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                transfer_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0.0,
                speed_mbps REAL NOT NULL DEFAULT 0.0,
                error_message TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT,
                timestamp TEXT NOT NULL
            );
            """)
            conn.commit()

    # --- Node Operations ---

    def register_or_update_node(self, node: NodeModel) -> NodeModel:
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO nodes (node_id, hostname, ip, port, total_storage, available_storage, status, last_heartbeat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                hostname=excluded.hostname,
                ip=excluded.ip,
                port=excluded.port,
                total_storage=excluded.total_storage,
                available_storage=excluded.available_storage,
                status=excluded.status,
                last_heartbeat=excluded.last_heartbeat;
            """, (
                node.node_id, node.hostname, node.ip, node.port,
                node.total_storage, node.available_storage,
                node.status.value, node.last_heartbeat.isoformat()
            ))
            conn.commit()
        return node

    def update_node_heartbeat(self, node_id: str, available_storage: int, total_storage: int, status: NodeStatus) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.execute("""
            UPDATE nodes SET
                available_storage = ?,
                total_storage = ?,
                status = ?,
                last_heartbeat = ?
            WHERE node_id = ?;
            """, (available_storage, total_storage, status.value, now_iso, node_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_node_status(self, node_id: str, status: NodeStatus) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("UPDATE nodes SET status = ? WHERE node_id = ?;", (status.value, node_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_node(self, node_id: str) -> Optional[NodeModel]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE node_id = ?;", (node_id,)).fetchone()
            if row:
                return NodeModel(
                    node_id=row["node_id"],
                    hostname=row["hostname"],
                    ip=row["ip"],
                    port=row["port"],
                    total_storage=row["total_storage"],
                    available_storage=row["available_storage"],
                    status=NodeStatus(row["status"]),
                    last_heartbeat=datetime.fromisoformat(row["last_heartbeat"])
                )
        return None

    def list_nodes(self) -> List[NodeModel]:
        nodes = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM nodes ORDER BY node_id;").fetchall()
            for r in rows:
                nodes.append(NodeModel(
                    node_id=r["node_id"],
                    hostname=r["hostname"],
                    ip=r["ip"],
                    port=r["port"],
                    total_storage=r["total_storage"],
                    available_storage=r["available_storage"],
                    status=NodeStatus(r["status"]),
                    last_heartbeat=datetime.fromisoformat(r["last_heartbeat"])
                ))
        return nodes

    # --- File Operations ---

    def create_file(self, file_model: FileModel) -> FileModel:
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO files (file_id, filename, size, created_at, overall_hash, status, chunk_size, replication_factor, encrypted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                file_model.file_id, file_model.filename, file_model.size,
                file_model.created_at.isoformat(), file_model.overall_hash,
                file_model.status.value, file_model.chunk_size,
                file_model.replication_factor, 1 if file_model.encrypted else 0
            ))
            conn.commit()
        return file_model

    def update_file_status(self, file_id: str, status: FileStatus) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("UPDATE files SET status = ? WHERE file_id = ?;", (status.value, file_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_file(self, file_id: str) -> Optional[FileModel]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM files WHERE file_id = ?;", (file_id,)).fetchone()
            if row:
                return FileModel(
                    file_id=row["file_id"],
                    filename=row["filename"],
                    size=row["size"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    overall_hash=row["overall_hash"],
                    status=FileStatus(row["status"]),
                    chunk_size=row["chunk_size"],
                    replication_factor=row["replication_factor"],
                    encrypted=bool(row["encrypted"])
                )
        return None

    def list_files(self) -> List[FileModel]:
        files = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM files ORDER BY created_at DESC;").fetchall()
            for r in rows:
                files.append(FileModel(
                    file_id=r["file_id"],
                    filename=r["filename"],
                    size=r["size"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    overall_hash=r["overall_hash"],
                    status=FileStatus(r["status"]),
                    chunk_size=r["chunk_size"],
                    replication_factor=r["replication_factor"],
                    encrypted=bool(r["encrypted"])
                ))
        return files

    def delete_file(self, file_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM files WHERE file_id = ?;", (file_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Chunk & Replica Operations ---

    def create_chunks(self, chunks: List[ChunkModel]):
        with self.get_connection() as conn:
            conn.executemany("""
            INSERT INTO chunks (chunk_id, file_id, sequence_number, size, sha256)
            VALUES (?, ?, ?, ?, ?);
            """, [(c.chunk_id, c.file_id, c.sequence_number, c.size, c.sha256) for c in chunks])
            conn.commit()

    def get_chunks_for_file(self, file_id: str) -> List[ChunkModel]:
        chunks = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM chunks WHERE file_id = ? ORDER BY sequence_number ASC;", (file_id,)).fetchall()
            for r in rows:
                chunks.append(ChunkModel(
                    chunk_id=r["chunk_id"],
                    file_id=r["file_id"],
                    sequence_number=r["sequence_number"],
                    size=r["size"],
                    sha256=r["sha256"]
                ))
        return chunks

    def add_replica(self, replica: ChunkReplicaModel) -> ChunkReplicaModel:
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO chunk_replicas (chunk_id, node_id, replica_number, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chunk_id, node_id) DO UPDATE SET
                status=excluded.status,
                replica_number=excluded.replica_number;
            """, (
                replica.chunk_id, replica.node_id, replica.replica_number,
                replica.status.value, replica.created_at.isoformat()
            ))
            conn.commit()
        return replica

    def update_replica_status(self, chunk_id: str, node_id: str, status: ReplicaStatus) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE chunk_replicas SET status = ? WHERE chunk_id = ? AND node_id = ?;",
                (status.value, chunk_id, node_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_replica(self, chunk_id: str, node_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM chunk_replicas WHERE chunk_id = ? AND node_id = ?;", (chunk_id, node_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_replicas_for_chunk(self, chunk_id: str) -> List[ChunkReplicaModel]:
        replicas = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM chunk_replicas WHERE chunk_id = ?;", (chunk_id,)).fetchall()
            for r in rows:
                replicas.append(ChunkReplicaModel(
                    chunk_id=r["chunk_id"],
                    node_id=r["node_id"],
                    replica_number=r["replica_number"],
                    status=ReplicaStatus(r["status"]),
                    created_at=datetime.fromisoformat(r["created_at"])
                ))
        return replicas

    def get_replicas_for_node(self, node_id: str) -> List[ChunkReplicaModel]:
        replicas = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM chunk_replicas WHERE node_id = ?;", (node_id,)).fetchall()
            for r in rows:
                replicas.append(ChunkReplicaModel(
                    chunk_id=r["chunk_id"],
                    node_id=r["node_id"],
                    replica_number=r["replica_number"],
                    status=ReplicaStatus(r["status"]),
                    created_at=datetime.fromisoformat(r["created_at"])
                ))
        return replicas

    def get_all_replicas_for_file(self, file_id: str) -> List[ChunkReplicaModel]:
        replicas = []
        with self.get_connection() as conn:
            rows = conn.execute("""
            SELECT cr.* FROM chunk_replicas cr
            JOIN chunks c ON cr.chunk_id = c.chunk_id
            WHERE c.file_id = ?;
            """, (file_id,)).fetchall()
            for r in rows:
                replicas.append(ChunkReplicaModel(
                    chunk_id=r["chunk_id"],
                    node_id=r["node_id"],
                    replica_number=r["replica_number"],
                    status=ReplicaStatus(r["status"]),
                    created_at=datetime.fromisoformat(r["created_at"])
                ))
        return replicas

    # --- Transfers & Events ---

    def create_transfer(self, transfer: TransferModel) -> TransferModel:
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO transfers (transfer_id, file_id, transfer_type, status, progress, speed_mbps, error_message, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                transfer.transfer_id, transfer.file_id, transfer.transfer_type.value,
                transfer.status.value, transfer.progress, transfer.speed_mbps,
                transfer.error_message, transfer.started_at.isoformat(),
                transfer.completed_at.isoformat() if transfer.completed_at else None
            ))
            conn.commit()
        return transfer

    def update_transfer(
        self,
        transfer_id: str,
        progress: float,
        speed_mbps: float = 0.0,
        status: Optional[TransferStatus] = None,
        error_message: Optional[str] = None
    ) -> bool:
        completed_at_iso = datetime.now(timezone.utc).isoformat() if status in (TransferStatus.COMPLETED, TransferStatus.FAILED) else None
        with self.get_connection() as conn:
            if status:
                cursor = conn.execute("""
                UPDATE transfers SET progress = ?, speed_mbps = ?, status = ?, error_message = ?, completed_at = COALESCE(completed_at, ?)
                WHERE transfer_id = ?;
                """, (progress, speed_mbps, status.value, error_message, completed_at_iso, transfer_id))
            else:
                cursor = conn.execute("""
                UPDATE transfers SET progress = ?, speed_mbps = ?
                WHERE transfer_id = ?;
                """, (progress, speed_mbps, transfer_id))
            conn.commit()
            return cursor.rowcount > 0

    def list_transfers(self, limit: int = 50) -> List[TransferModel]:
        transfers = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM transfers ORDER BY started_at DESC LIMIT ?;", (limit,)).fetchall()
            for r in rows:
                transfers.append(TransferModel(
                    transfer_id=r["transfer_id"],
                    file_id=r["file_id"],
                    transfer_type=TransferType(r["transfer_type"]),
                    status=TransferStatus(r["status"]),
                    progress=r["progress"],
                    speed_mbps=r["speed_mbps"],
                    error_message=r["error_message"],
                    started_at=datetime.fromisoformat(r["started_at"]),
                    completed_at=datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None
                ))
        return transfers

    def add_event(self, event: EventModel) -> EventModel:
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO events (event_id, event_type, message, details_json, timestamp)
            VALUES (?, ?, ?, ?, ?);
            """, (
                event.event_id, event.event_type.value, event.message,
                json.dumps(event.details) if event.details else None,
                event.timestamp.isoformat()
            ))
            conn.commit()
        return event

    def list_events(self, limit: int = 50) -> List[EventModel]:
        events = []
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?;", (limit,)).fetchall()
            for r in rows:
                events.append(EventModel(
                    event_id=r["event_id"],
                    event_type=EventType(r["event_type"]),
                    message=r["message"],
                    details=json.loads(r["details_json"]) if r["details_json"] else None,
                    timestamp=datetime.fromisoformat(r["timestamp"])
                ))
        return events
