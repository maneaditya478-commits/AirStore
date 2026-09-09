import os
import shutil
import psutil
from pathlib import Path
from typing import Dict, Any, Optional
from airstore.core.hashing import calculate_bytes_hash, calculate_file_hash
from airstore.core.chunking import IntegrityError

class StorageEngine:
    """
    Manages local chunk storage on disk for a single storage node.
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir).resolve()
        self.chunks_dir = self.storage_dir / "chunks"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def get_chunk_path(self, chunk_id: str) -> Path:
        """Sanitize and get path for chunk file."""
        safe_id = "".join(c for c in chunk_id if c.isalnum() or c in ("-", "_"))
        return self.chunks_dir / f"{safe_id}.chunk"

    def chunk_exists(self, chunk_id: str) -> bool:
        return self.get_chunk_path(chunk_id).exists()

    def store_chunk(self, chunk_id: str, data: bytes, expected_sha256: Optional[str] = None) -> int:
        """
        Store chunk data to disk. Verify integrity hash if expected_sha256 is provided.
        Returns size in bytes stored.
        """
        if expected_sha256:
            calculated = calculate_bytes_hash(data)
            if calculated != expected_sha256:
                raise IntegrityError(f"Chunk {chunk_id} integrity mismatch. Expected {expected_sha256}, got {calculated}")

        path = self.get_chunk_path(chunk_id)
        temp_path = path.with_suffix(".tmp")

        try:
            with open(temp_path, "wb") as f:
                f.write(data)

            if path.exists():
                os.remove(path)
            os.rename(temp_path, path)
            return len(data)
        except Exception as e:
            if temp_path.exists():
                os.remove(temp_path)
            raise e

    def retrieve_chunk(self, chunk_id: str) -> bytes:
        """Retrieve raw chunk bytes from disk."""
        path = self.get_chunk_path(chunk_id)
        if not path.exists():
            raise FileNotFoundError(f"Chunk {chunk_id} not found on node storage.")
        return path.read_bytes()

    def delete_chunk(self, chunk_id: str) -> bool:
        """Delete chunk from disk."""
        path = self.get_chunk_path(chunk_id)
        if path.exists():
            os.remove(path)
            return True
        return False

    def verify_chunk(self, chunk_id: str, expected_sha256: str) -> bool:
        """Verify local chunk file integrity against expected hash."""
        path = self.get_chunk_path(chunk_id)
        if not path.exists():
            return False
        calculated = calculate_file_hash(path)
        return calculated == expected_sha256

    def get_stats(self) -> Dict[str, Any]:
        """Return storage usage statistics for this node's disk/directory."""
        usage = psutil.disk_usage(str(self.storage_dir))
        chunk_files = list(self.chunks_dir.glob("*.chunk"))
        used_by_chunks = sum(f.stat().st_size for f in chunk_files if f.exists())

        return {
            "total_storage": usage.total,
            "available_storage": usage.free,
            "used_storage": usage.used,
            "airstore_chunk_bytes": used_by_chunks,
            "chunk_count": len(chunk_files)
        }
