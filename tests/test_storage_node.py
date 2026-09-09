import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from airstore.core.hashing import calculate_bytes_hash
from airstore.node.storage import StorageEngine
from airstore.node.main import create_node_app

def test_storage_engine(tmp_path):
    engine = StorageEngine(tmp_path)
    data = b"AirStore node storage engine unit test data."
    sha256 = calculate_bytes_hash(data)
    chunk_id = "test_chunk_001"

    # Store
    stored_bytes = engine.store_chunk(chunk_id, data, expected_sha256=sha256)
    assert stored_bytes == len(data)
    assert engine.chunk_exists(chunk_id)

    # Retrieve
    retrieved = engine.retrieve_chunk(chunk_id)
    assert retrieved == data

    # Verify
    assert engine.verify_chunk(chunk_id, sha256) is True
    assert engine.verify_chunk(chunk_id, "wrong_hash") is False

    # Stats
    stats = engine.get_stats()
    assert stats["chunk_count"] == 1
    assert stats["airstore_chunk_bytes"] == len(data)

    # Delete
    assert engine.delete_chunk(chunk_id) is True
    assert not engine.chunk_exists(chunk_id)

def test_storage_node_api(tmp_path):
    node_dir = tmp_path / "node_a"
    app = create_node_app(
        node_id="node_a",
        storage_dir=node_dir,
        auto_register=False  # disable auto manager registration in unit test
    )
    client = TestClient(app)

    # Health
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == "node_a"

    # PUT Chunk with correct hash
    chunk_data = b"Chunk bytes via REST API"
    chunk_sha = calculate_bytes_hash(chunk_data)
    resp = client.put(f"/chunks/chunk_101?sha256={chunk_sha}", content=chunk_data)
    assert resp.status_code == 200
    assert resp.json()["bytes_stored"] == len(chunk_data)

    # PUT Chunk with corrupted hash -> Should fail
    resp = client.put("/chunks/chunk_102?sha256=invalidhash", content=chunk_data)
    assert resp.status_code == 400

    # GET Chunk
    resp = client.get("/chunks/chunk_101")
    assert resp.status_code == 200
    assert resp.content == chunk_data

    # Verify endpoint
    resp = client.get(f"/chunks/chunk_101/verify?sha256={chunk_sha}")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    # DELETE Chunk
    resp = client.delete("/chunks/chunk_101")
    assert resp.status_code == 200

    # GET Deleted Chunk -> 404
    resp = client.get("/chunks/chunk_101")
    assert resp.status_code == 404
