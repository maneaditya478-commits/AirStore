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

def test_e2e_final_acceptance(tmp_path):
    """
    Final Acceptance Test:
    1. Start Manager + Node A + Node B + Node C
    2. Upload test file
    3. Verify chunks and 2x replicas
    4. Shut down Node B
    5. Detect failure and trigger auto-recovery
    6. Verify new replica created on surviving healthy nodes
    7. Download file and verify SHA-256 matches original file.
    """
    mgr_db = tmp_path / "e2e_manager.db"
    mgr_app = create_manager_app(db_path=mgr_db, start_monitor=False)
    mgr_port = get_free_port()
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    nodes_info = []
    node_servers = []

    for name in ["Node_A", "Node_B", "Node_C"]:
        port = get_free_port()
        dir_path = tmp_path / name
        n_app = create_node_app(
            node_id=name,
            storage_dir=dir_path,
            manager_url=mgr_url,
            host="127.0.0.1",
            port=port,
            auto_register=True
        )
        srv = ServerThread(n_app, "127.0.0.1", port)
        srv.start()
        node_servers.append(srv)
        nodes_info.append({"id": name, "port": port, "dir": dir_path})

    time.sleep(1.0)  # Wait for startup & cluster registration

    try:
        db = mgr_app.state.db
        storage_svc = mgr_app.state.storage_service
        recovery_svc = mgr_app.state.recovery_service

        # 1. Verify 3 nodes registered
        active_nodes = db.list_nodes()
        assert len(active_nodes) == 3

        # 2. Create 3 MB binary test file
        test_file = tmp_path / "research_dataset.zip"
        test_data = os.urandom(3 * 1024 * 1024)
        test_file.write_bytes(test_data)
        original_hash = calculate_file_hash(test_file)

        # 3. Upload file with 512KB chunks, replication factor 2
        uploaded_file = storage_svc.process_file_upload(
            source_file_path=test_file,
            filename="research_dataset.zip",
            chunk_size=512 * 1024,
            replication_factor=2
        )

        assert uploaded_file.status == FileStatus.ACTIVE
        chunks = db.get_chunks_for_file(uploaded_file.file_id)
        assert len(chunks) == 6

        all_replicas = db.get_all_replicas_for_file(uploaded_file.file_id)
        assert len(all_replicas) == 12  # 6 chunks * 2 replicas

        # 4. Shut down Node_B
        node_b_idx = [i for i, n in enumerate(nodes_info) if n["id"] == "Node_B"][0]
        node_servers[node_b_idx].stop()
        time.sleep(0.5)

        # 5. Recovery triggers
        rec_res = recovery_svc.recover_node_failure("Node_B")
        assert rec_res["status"] == "COMPLETED"

        # Node_B must be OFFLINE in DB
        node_b_db = db.get_node("Node_B")
        assert node_b_db.status == NodeStatus.OFFLINE

        # 6. Verify chunks still have 2 healthy replicas (on Node_A and Node_C)
        for chunk in chunks:
            reps = db.get_replicas_for_chunk(chunk.chunk_id)
            stored_reps = [r for r in reps if r.status == ReplicaStatus.STORED]
            assert len(stored_reps) == 2
            assert "Node_B" not in [r.node_id for r in stored_reps]

        # 7. Download file and verify SHA-256
        recovered_path = tmp_path / "downloaded_research_dataset.zip"
        download_success = storage_svc.stream_file_reconstruction(
            uploaded_file.file_id, recovered_path
        )

        assert download_success is True
        assert recovered_path.exists()
        recovered_hash = calculate_file_hash(recovered_path)

        print("\n==========================================")
        print("FINAL ACCEPTANCE VERIFICATION RESULT")
        print("==========================================")
        print(f"ORIGINAL HASH:  {original_hash}")
        print(f"RECOVERED HASH: {recovered_hash}")
        print("RESULT:         PASS")
        print("==========================================\n")

        assert original_hash == recovered_hash
        assert recovered_path.read_bytes() == test_data

    finally:
        for srv in node_servers:
            srv.stop()
        mgr_srv.stop()
