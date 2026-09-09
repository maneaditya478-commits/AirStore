import os
import time
import socket
import pytest
import uvicorn
import threading
from concurrent.futures import ThreadPoolExecutor
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

def test_concurrent_uploads_and_downloads(tmp_path):
    mgr_db = tmp_path / "concurrent_mgr.db"
    mgr_app = create_manager_app(db_path=mgr_db, start_monitor=False)
    mgr_port = get_free_port()
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    nodes_servers = []
    for name in ["conc_node_1", "conc_node_2", "conc_node_3"]:
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
        # Create 3 test files
        files_to_upload = []
        for i in range(3):
            p = tmp_path / f"conc_file_{i}.bin"
            data = os.urandom(1 * 1024 * 1024)
            p.write_bytes(data)
            files_to_upload.append({"path": p, "data": data, "hash": calculate_file_hash(p)})

        # Upload 3 files concurrently using ThreadPoolExecutor
        def upload_worker(item):
            return storage_svc.process_file_upload(
                source_file_path=item["path"],
                filename=item["path"].name,
                chunk_size=256 * 1024,
                replication_factor=2
            )

        with ThreadPoolExecutor(max_workers=3) as executor:
            uploaded_models = list(executor.map(upload_worker, files_to_upload))

        assert len(uploaded_models) == 3
        for model in uploaded_models:
            assert model.status == FileStatus.ACTIVE

        # Download 3 files concurrently
        def download_worker(arg):
            file_id, out_p = arg
            return storage_svc.stream_file_reconstruction(file_id, out_p)

        download_tasks = []
        for i, model in enumerate(uploaded_models):
            out_p = tmp_path / f"conc_download_{i}.bin"
            download_tasks.append((model.file_id, out_p))

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(download_worker, download_tasks))

        assert all(results)

        for i, (_, out_p) in enumerate(download_tasks):
            assert out_p.exists()
            assert calculate_file_hash(out_p) == files_to_upload[i]["hash"]

    finally:
        for srv in nodes_servers:
            srv.stop()
        mgr_srv.stop()
