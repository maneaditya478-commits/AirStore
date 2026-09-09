import os
import socket
import time
import pytest
import uvicorn
import threading
from pathlib import Path
from airstore.core.hashing import calculate_file_hash
from airstore.core.models import NodeStatus, ReplicaStatus, FileStatus
from airstore.manager.main import create_manager_app
from airstore.node.main import create_node_app
from airstore.manager.services.storage_manager import StorageManagerService
from airstore.manager.services.recovery_service import RecoveryService
from airstore.manager.database.db import DatabaseManager

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
        self.host = host
        self.port = port

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def test_failure_detection_and_recovery(tmp_path):
    mgr_db_path = tmp_path / "mgr_recovery.db"
    mgr_app = create_manager_app(db_path=mgr_db_path, start_monitor=False)
    mgr_port = get_free_port()
    mgr_server = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_server.start()
    
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    # Spin up 3 storage nodes
    nodes = []
    servers = []
    for i, name in enumerate(["node_A", "node_B", "node_C"]):
        port = get_free_port()
        node_dir = tmp_path / name
        node_app = create_node_app(
            node_id=name,
            storage_dir=node_dir,
            manager_url=mgr_url,
            host="127.0.0.1",
            port=port,
            auto_register=True
        )
        srv = ServerThread(node_app, "127.0.0.1", port)
        srv.start()
        servers.append(srv)
        nodes.append({"id": name, "port": port, "dir": node_dir})

    time.sleep(1.0)  # Wait for startup & registration

    try:
        db = mgr_app.state.db
        storage_svc = mgr_app.state.storage_service
        recovery_svc = mgr_app.state.recovery_service

        db_nodes = db.list_nodes()
        assert len(db_nodes) == 3

        # Create 2MB test file
        test_file = tmp_path / "dataset_test.bin"
        test_bytes = os.urandom(2 * 1024 * 1024)
        test_file.write_bytes(test_bytes)
        original_hash = calculate_file_hash(test_file)

        # Upload file with chunk_size 512KB and replication_factor 2
        uploaded_file = storage_svc.process_file_upload(
            source_file_path=test_file,
            filename="dataset_test.bin",
            chunk_size=512 * 1024,
            replication_factor=2
        )

        assert uploaded_file.status == FileStatus.ACTIVE
        chunks = db.get_chunks_for_file(uploaded_file.file_id)
        assert len(chunks) == 4

        # Check replica distribution
        all_replicas = db.get_all_replicas_for_file(uploaded_file.file_id)
        assert len(all_replicas) == 8  # 4 chunks * 2 replicas

        # Pick whichever node actually holds replicas to simulate failure on
        node_counts = {}
        for r in all_replicas:
            node_counts[r.node_id] = node_counts.get(r.node_id, 0) + 1

        failed_node_id = list(node_counts.keys())[0]
        failed_node_replicas = db.get_replicas_for_node(failed_node_id)
        assert len(failed_node_replicas) > 0

        # Find the server index matching failed_node_id
        failed_server_idx = [i for i, n in enumerate(nodes) if n["id"] == failed_node_id][0]

        # --- SIMULATE FAILURE ---
        servers[failed_server_idx].stop()
        time.sleep(0.5)

        rec_result = recovery_svc.recover_node_failure(failed_node_id)
        assert rec_result["status"] == "COMPLETED"
        assert rec_result["recovered_chunks"] == len(failed_node_replicas)

        # Verify failed node is now OFFLINE in DB
        failed_node_db = db.get_node(failed_node_id)
        assert failed_node_db.status == NodeStatus.OFFLINE

        # Verify failed node's replicas were marked MISSING
        updated_failed_node_replicas = db.get_replicas_for_node(failed_node_id)
        for r in updated_failed_node_replicas:
            assert r.status == ReplicaStatus.MISSING

        # Check that replacement replicas were created on remaining healthy nodes
        for chunk in chunks:
            reps = db.get_replicas_for_chunk(chunk.chunk_id)
            stored_reps = [r for r in reps if r.status == ReplicaStatus.STORED]
            # Must still have 2 healthy STORED replicas
            assert len(stored_reps) == 2
            # None of stored replicas are on failed_node_id
            assert failed_node_id not in [r.node_id for r in stored_reps]

        # --- RECONSTRUCT AND VERIFY FILE AFTER RECOVERY ---
        output_reconstructed = tmp_path / "recovered_dataset.bin"
        reconstruct_success = storage_svc.stream_file_reconstruction(
            uploaded_file.file_id, output_reconstructed
        )
        assert reconstruct_success is True
        assert output_reconstructed.exists()

        recovered_hash = calculate_file_hash(output_reconstructed)
        assert recovered_hash == original_hash
        assert output_reconstructed.read_bytes() == test_bytes

    finally:
        for srv in servers:
            srv.stop()
        mgr_server.stop()
