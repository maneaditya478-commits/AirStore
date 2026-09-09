import uuid
import os
from pathlib import Path
from typing import Generator, Tuple, List, Union, BinaryIO
from airstore.core.models import ChunkModel
from airstore.core.hashing import calculate_bytes_hash, IncrementalHasher
from airstore.core.config import settings

class IntegrityError(Exception):
    """Exception raised when file or chunk SHA-256 hash fails verification."""
    pass

class FileChunker:
    """
    Handles memory-efficient streaming chunking and file reconstruction.
    """

    @staticmethod
    def get_file_info_and_chunks(
        file_path: Union[str, Path],
        file_id: str,
        chunk_size: int = settings.CHUNK_SIZE
    ) -> Tuple[str, int, List[ChunkModel]]:
        """
        Inspect file, calculate overall SHA-256 hash and metadata for all chunks without retaining chunk bytes in memory.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")

        file_size = path.stat().st_size
        overall_hasher = IncrementalHasher()
        chunks: List[ChunkModel] = []
        sequence = 0

        with open(path, "rb") as f:
            while True:
                # Read single chunk
                chunk_bytes = f.read(chunk_size)
                if not chunk_bytes:
                    break
                
                overall_hasher.update(chunk_bytes)
                chunk_hash = calculate_bytes_hash(chunk_bytes)
                chunk_id = f"{file_id}_chunk_{sequence:06d}"
                
                chunk_model = ChunkModel(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    sequence_number=sequence,
                    size=len(chunk_bytes),
                    sha256=chunk_hash
                )
                chunks.append(chunk_model)
                sequence += 1

        overall_hash = overall_hasher.hexdigest()
        return overall_hash, file_size, chunks

    @staticmethod
    def stream_chunks(
        file_path: Union[str, Path],
        file_id: str,
        chunk_size: int = settings.CHUNK_SIZE
    ) -> Generator[Tuple[ChunkModel, bytes], None, None]:
        """
        Generator yielding (ChunkModel, chunk_bytes) one chunk at a time.
        Memory footprint is limited to max chunk_size.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")

        sequence = 0
        with open(path, "rb") as f:
            while True:
                chunk_bytes = f.read(chunk_size)
                if not chunk_bytes:
                    break
                
                chunk_hash = calculate_bytes_hash(chunk_bytes)
                chunk_id = f"{file_id}_chunk_{sequence:06d}"
                
                chunk_model = ChunkModel(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    sequence_number=sequence,
                    size=len(chunk_bytes),
                    sha256=chunk_hash
                )
                yield chunk_model, chunk_bytes
                sequence += 1

    @staticmethod
    def assemble_file_from_stream(
        chunk_stream: Generator[bytes, None, None],
        output_path: Union[str, Path],
        expected_overall_hash: str,
        buffer_size: int = 64 * 1024
    ) -> bool:
        """
        Stream chunks into output file and verify overall SHA-256 hash.
        If hash mismatch occurs, output file is deleted and IntegrityError is raised.
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        temp_path = out_p.with_suffix(out_p.suffix + ".tmp")

        hasher = IncrementalHasher()

        try:
            with open(temp_path, "wb") as f:
                for chunk_bytes in chunk_stream:
                    hasher.update(chunk_bytes)
                    f.write(chunk_bytes)
            
            calculated_hash = hasher.hexdigest()
            if calculated_hash != expected_overall_hash:
                if temp_path.exists():
                    os.remove(temp_path)
                raise IntegrityError(
                    f"File integrity check failed! Expected hash: {expected_overall_hash}, got: {calculated_hash}"
                )

            # Atomic move / rename
            if temp_path.exists():
                if out_p.exists():
                    os.remove(out_p)
                os.rename(temp_path, out_p)
            return True

        except Exception as e:
            if temp_path.exists():
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise e
