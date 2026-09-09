import os
import time
import json
import socket
import pytest
import uvicorn
import threading
from pathlib import Path
from airstore.manager.main import create_manager_app
from airstore.node.main import create_node_app
from scripts.lan_test import run_lan_validation

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

def test_lan_validation_tooling(tmp_path):
    mgr_db = tmp_path / "lan_tool_mgr.db"
    mgr_app = create_manager_app(db_path=mgr_db, start_monitor=False)
    mgr_port = get_free_port()
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    mgr_url = f"http://127.0.0.1:{mgr_port}"
    time.sleep(1.0)  # Wait for manager server thread to initialize and bind port

    nodes_servers = []
    for name in ["lan_node_1", "lan_node_2"]:
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
        time.sleep(0.3)

    time.sleep(2.0)
    db = mgr_app.state.db
    for _ in range(20):
        if len(db.list_nodes()) == 2:
            break
        time.sleep(0.5)

    out_dir = tmp_path / "research_results"

    try:
        run_lan_validation(manager_url=mgr_url, output_dir=out_dir)

        json_file = out_dir / "lan_test_results.json"
        txt_file = out_dir / "lan_test_report.txt"

        assert json_file.exists()
        assert txt_file.exists()

        with open(json_file, "r") as f:
            data = json.load(f)

        assert data["status"] == "PASS"
        assert data["integrity_verified"] is True
        assert len(data["nodes"]) == 2
        assert data["upload_test"]["speed_mbps"] > 0
        assert data["download_test"]["sha256_match"] is True

    finally:
        for srv in nodes_servers:
            srv.stop()
        mgr_srv.stop()
