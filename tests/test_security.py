import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from airstore.node.main import create_node_app
from airstore.manager.main import create_manager_app

def test_path_traversal_prevention(tmp_path):
    node_app = create_node_app(
        node_id="sec_node",
        storage_dir=tmp_path / "sec_storage",
        auto_register=False
    )
    client = TestClient(node_app)

    # Attempt path traversal on PUT /chunks/{chunk_id}
    resp = client.put("/chunks/..%2F..%2Fetc%2Fpasswd", content=b"malicious data")
    assert resp.status_code in (400, 404)

    # Attempt path traversal on GET /chunks/{chunk_id}
    resp = client.get("/chunks/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)

def test_upload_check_endpoint(tmp_path):
    mgr_app = create_manager_app(db_path=tmp_path / "sec_mgr.db", start_monitor=False)
    client = TestClient(mgr_app)

    check_payload = {
        "filename": "dataset.zip",
        "chunks": []
    }
    resp = client.post("/api/files/upload/check", json=check_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "resumable" in data
    assert "existing_chunks" in data

def test_metrics_endpoint(tmp_path):
    mgr_app = create_manager_app(db_path=tmp_path / "sec_metrics.db", start_monitor=False)
    client = TestClient(mgr_app)

    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    m = resp.json()
    assert "total_uploads" in m
    assert "upload_throughput_mbps" in m
    assert "storage_utilization_pct" in m
