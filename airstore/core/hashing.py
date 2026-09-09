import hashlib
from typing import BinaryIO, Union
from pathlib import Path

def calculate_bytes_hash(data: bytes) -> str:
    """Calculate SHA-256 hash of a byte string."""
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest()

def calculate_file_hash(file_path: Union[str, Path], buffer_size: int = 64 * 1024) -> str:
    """Calculate SHA-256 hash of a file streaming in chunks (memory safe)."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(buffer_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

class IncrementalHasher:
    """Incremental SHA-256 hasher for processing data streams."""
    def __init__(self):
        self._hasher = hashlib.sha256()
        self._bytes_processed = 0

    def update(self, data: bytes) -> None:
        self._hasher.update(data)
        self._bytes_processed += len(data)

    def digest(self) -> bytes:
        return self._hasher.digest()

    def hexdigest(self) -> str:
        return self._hasher.hexdigest()

    @property
    def bytes_processed(self) -> int:
        return self._bytes_processed
