import os
import sys
import time
import csv
import psutil
import socket
import uvicorn
import threading
from pathlib import Path
from airstore.core.config import settings
from airstore.core.hashing import calculate_file_hash
from airstore.core.models import NodeStatus
from airstore.manager.main import create_manager_app
from airstore.node.main import create_node_app

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="error"))

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def run_benchmark(output_csv: Path = Path("benchmark_results.csv")):
    print("==================================================")
    print("       AirStore Performance Benchmark Suite       ")
    print("==================================================")

    process = psutil.Process(os.getpid())
    results = []

    # Temporary directory for benchmark
    tmp_dir = Path("data/benchmark_scratch")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Setup Manager + 3 Nodes
    mgr_port = get_free_port()
    mgr_app = create_manager_app(db_path=tmp_dir / "bench_mgr.db", start_monitor=False)
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    nodes = []
    node_servers = []
    for i in range(3):
        node_id = f"bench_node_{i+1}"
        port = get_free_port()
        n_app = create_node_app(
            node_id=node_id,
            storage_dir=tmp_dir / node_id,
            manager_url=mgr_url,
            host="127.0.0.1",
            port=port,
            auto_register=True
        )
        srv = ServerThread(n_app, "127.0.0.1", port)
        srv.start()
        node_servers.append(srv)
        nodes.append(node_id)

    time.sleep(2.0)
    db = mgr_app.state.db
    # Wait for nodes to register
    for _ in range(20):
        if len(db.list_nodes()) == 3:
            break
        time.sleep(0.5)

    storage_svc = mgr_app.state.storage_service
    recovery_svc = mgr_app.state.recovery_service

    # Test matrix
    file_sizes_mb = [1, 5, 10]
    chunk_sizes_kb = [256, 512, 1024]
    replication_factors = [1, 2]

    try:
        for size_mb in file_sizes_mb:
            for chunk_kb in chunk_sizes_kb:
                for repl in replication_factors:
                    chunk_bytes = chunk_kb * 1024
                    file_bytes = size_mb * 1024 * 1024
                    
                    # Create test file
                    test_file = tmp_dir / f"test_{size_mb}MB.bin"
                    if not test_file.exists() or test_file.stat().st_size != file_bytes:
                        test_file.write_bytes(os.urandom(file_bytes))

                    # Measure Upload
                    cpu_before = process.cpu_percent()
                    mem_before = process.memory_info().rss / (1024 * 1024)
                    
                    t0 = time.time()
                    uploaded = storage_svc.process_file_upload(
                        source_file_path=test_file,
                        filename=test_file.name,
                        chunk_size=chunk_bytes,
                        replication_factor=repl
                    )
                    t_upload = time.time() - t0
                    upload_mbps = round((size_mb * repl) / max(t_upload, 0.001), 2)

                    # Measure Download
                    dl_file = tmp_dir / f"dl_{size_mb}MB.bin"
                    t1 = time.time()
                    storage_svc.stream_file_reconstruction(uploaded.file_id, dl_file)
                    t_download = time.time() - t1
                    download_mbps = round(size_mb / max(t_download, 0.001), 2)

                    cpu_after = process.cpu_percent()
                    mem_after = process.memory_info().rss / (1024 * 1024)

                    # Measure Recovery (if repl >= 2)
                    t_recovery = 0.0
                    if repl >= 2:
                        t2 = time.time()
                        rec_res = recovery_svc.recover_node_failure("bench_node_1")
                        t_recovery = time.time() - t2
                        mgr_app.state.db.update_node_status("bench_node_1", NodeStatus.ONLINE)

                    row = {
                        "file_size_mb": size_mb,
                        "chunk_size_kb": chunk_kb,
                        "replication_factor": repl,
                        "upload_time_sec": round(t_upload, 3),
                        "upload_throughput_mbps": upload_mbps,
                        "download_time_sec": round(t_download, 3),
                        "download_throughput_mbps": download_mbps,
                        "recovery_time_sec": round(t_recovery, 3),
                        "mem_usage_mb": round(mem_after, 2)
                    }
                    results.append(row)

                    print(f"[*] Benchmark -> Size: {size_mb}MB | Chunk: {chunk_kb}KB | Repl: {repl}x")
                    print(f"    Upload: {upload_mbps} MB/s | Download: {download_mbps} MB/s | Recovery: {round(t_recovery, 3)}s")

        # Write CSV
        with open(output_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

        print(f"\n[+] Benchmark suite completed! CSV report saved to '{output_csv.resolve()}'\n")

    finally:
        for srv in node_servers:
            srv.stop()
        mgr_srv.stop()

if __name__ == "__main__":
    csv_out = Path("benchmark_results.csv")
    run_benchmark(csv_out)
