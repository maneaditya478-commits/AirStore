import os
import time
import socket
import pytest
import uvicorn
import threading
from pathlib import Path
from airstore.core.hashing import calculate_file_hash
from airstore.core.models import FileStatus
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

def test_resumable_file_upload(tmp_path):
    mgr_db = tmp_path / "resumable_mgr.db"
    mgr_app = create_manager_app(db_path=mgr_db, start_monitor=False)
    mgr_port = get_free_port()
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    nodes_servers = []
    for name in ["res_node_1", "res_node_2"]:
        port = get_free_port()
        n_app = create_node_app(
            node_id=name,
            storage_dir=tmp_path / name,
            manager_url=mgr_url,
            host="127.0.0.1",
            port=port,
            auto_register=True
        )
        srv = ServerThread(n_app, "127.0.0.1", port)
        srv.start()
        nodes_servers.append(srv)

    time.sleep(1.0)
    storage_svc = mgr_app.state.storage_service

    try:
        # Create test file
        test_file = tmp_path / "resumable.dat"
        data = os.urandom(1 * 1024 * 1024)
        test_file.write_bytes(data)

        # Initial upload
        up1 = storage_svc.process_file_upload(
            source_file_path=test_file,
            filename="resumable.dat",
            chunk_size=256 * 1024,
            replication_factor=2
        )
        assert up1.status == FileStatus.ACTIVE

        # Re-upload same file (simulating upload retry/resumption)
        t0 = time.time()
        up2 = storage_svc.process_file_upload(
            source_file_path=test_file,
            filename="resumable.dat",
            chunk_size=256 * 1024,
            replication_factor=2
        )
        t_elapsed = time.time() - t0
        
        assert up2.status == FileStatus.ACTIVE
        assert t_elapsed < 10.0

    finally:
        for srv in nodes_servers:
            srv.stop()
        mgr_srv.stop()
