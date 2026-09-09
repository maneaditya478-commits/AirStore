import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from airstore.core.models import (
    NodeModel, ChunkModel, NodeStatus, FileStatus, ReplicaStatus
)
from airstore.core.hashing import calculate_bytes_hash
from airstore.manager.database.db import DatabaseManager
from airstore.manager.placement import RuleBasedPlacementStrategy, InsufficientNodesError
from airstore.manager.main import create_manager_app
from airstore.node.main import create_node_app

def test_database_manager(tmp_path):
    db_path = tmp_path / "test_manager.db"
    db = DatabaseManager(db_path)

    # Node operations
    node1 = NodeModel(
        node_id="n1", hostname="host1", ip="127.0.0.1", port=8001,
        total_storage=100000, available_storage=80000, status=NodeStatus.ONLINE
    )
    db.register_or_update_node(node1)

    fetched_node = db.get_node("n1")
    assert fetched_node is not None
    assert fetched_node.hostname == "host1"

    nodes = db.list_nodes()
    assert len(nodes) == 1

    # Heartbeat update
    db.update_node_heartbeat("n1", available_storage=75000, total_storage=100000, status=NodeStatus.ONLINE)
    updated_node = db.get_node("n1")
    assert updated_node.available_storage == 75000

def test_rule_based_placement():
    strategy = RuleBasedPlacementStrategy()
    chunk = ChunkModel(chunk_id="c1", file_id="f1", sequence_number=0, size=1024, sha256="hash1")

    nodes = [
        NodeModel(node_id="n1", hostname="h1", ip="127.0.0.1", port=8001, total_storage=100, available_storage=5000, status=NodeStatus.ONLINE),
        NodeModel(node_id="n2", hostname="h2", ip="127.0.0.1", port=8002, total_storage=100, available_storage=10000, status=NodeStatus.ONLINE),
        NodeModel(node_id="n3", hostname="h3", ip="127.0.0.1", port=8003, total_storage=100, available_storage=2000, status=NodeStatus.ONLINE),
        NodeModel(node_id="n4", hostname="h4", ip="127.0.0.1", port=8004, total_storage=100, available_storage=20000, status=NodeStatus.OFFLINE)
    ]

    # Select 2 replicas
    selected = strategy.select_nodes_for_chunk(chunk, nodes, replication_factor=2)
    assert len(selected) == 2
    # Should pick n2 (10000 free) and n1 (5000 free) - highest available storage
    selected_ids = [n.node_id for n in selected]
    assert selected_ids == ["n2", "n1"]

    # Exclude n2 if replica already exists there
    selected_with_exclude = strategy.select_nodes_for_chunk(chunk, nodes, replication_factor=2, existing_replica_node_ids=["n2"])
    assert "n2" not in [n.node_id for n in selected_with_exclude]
    assert [n.node_id for n in selected_with_exclude] == ["n1", "n3"]

def test_manager_api(tmp_path):
    db_path = tmp_path / "mgr_api.db"
    manager_app = create_manager_app(db_path=db_path)
    client = TestClient(manager_app)

    # Register Node
    reg_payload = {
        "node_id": "node_001",
        "hostname": "localhost",
        "ip": "127.0.0.1",
        "port": 8001,
        "total_storage": 1000000,
        "available_storage": 900000,
        "auth_secret": "airstore-secret-cluster-auth-key"
    }
    resp = client.post("/api/nodes/register", json=reg_payload)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # List Nodes
    resp = client.get("/api/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "node_001"

    # Stats
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["online_nodes"] == 1
    assert stats["total_files"] == 0
