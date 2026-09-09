import os
import time
import socket
import pytest
import uvicorn
import threading
from pathlib import Path
from airstore.core.hashing import calculate_file_hash
from airstore.core.models import NodeStatus, ReplicaStatus
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

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def test_multi_node_failure_and_reconciliation(tmp_path):
    mgr_db = tmp_path / "adv_rec.db"
    mgr_app = create_manager_app(db_path=mgr_db, start_monitor=False)
    mgr_port = get_free_port()
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    nodes_info = []
    node_servers = []

    for name in ["adv_node_1", "adv_node_2", "adv_node_3"]:
        port = get_free_port()
        dir_p = tmp_path / name
        n_app = create_node_app(
            node_id=name,
            storage_dir=dir_p,
            manager_url=mgr_url,
            host="127.0.0.1",
            port=port,
            auto_register=True
        )
        srv = ServerThread(n_app, "127.0.0.1", port)
        srv.start()
        node_servers.append(srv)
        nodes_info.append({"id": name, "port": port, "dir": dir_p})

    time.sleep(1.0)
    db = mgr_app.state.db
    storage_svc = mgr_app.state.storage_service
    recovery_svc = mgr_app.state.recovery_service

    try:
        # Create test file
        test_f = tmp_path / "adv_data.bin"
        data = os.urandom(1 * 1024 * 1024)
        test_f.write_bytes(data)

        up = storage_svc.process_file_upload(
            source_file_path=test_f,
            filename="adv_data.bin",
            chunk_size=256 * 1024,
            replication_factor=2
        )

        # Audit consistency
        audit = recovery_svc.audit_replica_consistency()
        assert audit["healthy"] is True
        assert audit["stored_replicas"] == 8

        # Stop node 1
        node_servers[0].stop()
        time.sleep(0.5)

        # Recover node 1
        recovery_svc.recover_node_failure("adv_node_1")
        assert db.get_node("adv_node_1").status == NodeStatus.OFFLINE

        # Re-verify consistency
        audit_after = recovery_svc.audit_replica_consistency()
        assert audit_after["stored_replicas"] == 8  # Re-replicated onto healthy nodes

    finally:
        for srv in node_servers:
            srv.stop()
        mgr_srv.stop()
