import os
import pytest
import tempfile
from pathlib import Path
from airstore.core.models import (
    NodeModel, FileModel, ChunkModel, NodeStatus, FileStatus
)
from airstore.core.hashing import (
    calculate_bytes_hash, calculate_file_hash, IncrementalHasher
)
from airstore.core.encryption import ChunkEncryptor, EncryptionError
from airstore.core.chunking import FileChunker, IntegrityError

def test_models():
    node = NodeModel(
        node_id="node-1",
        hostname="localhost",
        ip="127.0.0.1",
        port=8001,
        total_storage=1000000,
        available_storage=500000
    )
    assert node.status == NodeStatus.ONLINE
    assert node.port == 8001

    file_meta = FileModel(
        file_id="file-123",
        filename="dataset.zip",
        size=1048576,
        overall_hash="abc123hash"
    )
    assert file_meta.status == FileStatus.ACTIVE
    assert file_meta.replication_factor == 2

def test_hashing(tmp_path):
    data = b"AirStore Offline Storage Network Test Bytes"
    expected_hash = calculate_bytes_hash(data)
    assert len(expected_hash) == 64

    # Test incremental hasher
    inc = IncrementalHasher()
    inc.update(data[:10])
    inc.update(data[10:])
    assert inc.hexdigest() == expected_hash

    # Test file hash
    test_file = tmp_path / "test.dat"
    test_file.write_bytes(data)
    assert calculate_file_hash(test_file) == expected_hash

def test_encryption():
    key = os.urandom(32)
    encryptor = ChunkEncryptor(key)
    plaintext = b"Sensitive storage chunk payload bytes 12345"

    # Encrypt
    encrypted_payload = encryptor.encrypt_chunk(plaintext)
    assert len(encrypted_payload) > len(plaintext)
    assert encrypted_payload != plaintext

    # Decrypt
    decrypted = encryptor.decrypt_chunk(encrypted_payload)
    assert decrypted == plaintext

    # Test tampering
    tampered_payload = bytearray(encrypted_payload)
    tampered_payload[-1] ^= 0xFF  # Corrupt last byte (tag)
    with pytest.raises(EncryptionError):
        encryptor.decrypt_chunk(bytes(tampered_payload))

def test_chunking_and_reconstruction(tmp_path):
    # Generate 1.5 MB test file
    test_file = tmp_path / "large_file.bin"
    chunk_size = 512 * 1024  # 512 KB chunks -> 3 chunks total
    data = os.urandom(1536 * 1024)
    test_file.write_bytes(data)

    original_hash, file_size, chunk_models = FileChunker.get_file_info_and_chunks(
        test_file, file_id="f1", chunk_size=chunk_size
    )

    assert file_size == len(data)
    assert len(chunk_models) == 3
    assert chunk_models[0].sequence_number == 0
    assert chunk_models[1].sequence_number == 1
    assert chunk_models[2].sequence_number == 2

    # Stream chunks and test individual hashes
    chunk_streams = list(FileChunker.stream_chunks(test_file, file_id="f1", chunk_size=chunk_size))
    assert len(chunk_streams) == 3

    for model, chunk_bytes in chunk_streams:
        assert calculate_bytes_hash(chunk_bytes) == model.sha256

    # Test successful file reconstruction
    output_file = tmp_path / "reconstructed.bin"
    def byte_generator():
        for _, cb in chunk_streams:
            yield cb

    success = FileChunker.assemble_file_from_stream(
        byte_generator(), output_file, expected_overall_hash=original_hash
    )
    assert success is True
    assert output_file.exists()
    assert output_file.read_bytes() == data

def test_chunking_integrity_failure(tmp_path):
    output_file = tmp_path / "failed_reconstructed.bin"
    corrupted_data = b"Corrupted chunk payload"
    expected_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    def byte_generator():
        yield corrupted_data

    with pytest.raises(IntegrityError):
        FileChunker.assemble_file_from_stream(
            byte_generator(), output_file, expected_overall_hash=expected_hash
        )

    # Ensure output file was not left behind
    assert not output_file.exists()
    assert not output_file.with_suffix(".tmp").exists()
