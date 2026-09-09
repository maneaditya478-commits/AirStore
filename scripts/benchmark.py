import os
import sys
import time
import csv
import json
import argparse
import psutil
import socket
import uvicorn
import threading
from pathlib import Path
from airstore.core.config import settings
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
        self.config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(self.config)

    def run(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def run_benchmark(
    output_csv: Path = Path("benchmark_results.csv"),
    output_json: Path = Path("research/results/raw/matrix_results.json"),
    num_nodes: int = 3,
    iterations: int = 1,
    file_sizes_mb: list = None,
    chunk_sizes_kb: list = None,
    replication_factors: list = None
):
    if file_sizes_mb is None:
        file_sizes_mb = [1, 5, 10]
    if chunk_sizes_kb is None:
        chunk_sizes_kb = [256, 512, 1024]
    if replication_factors is None:
        replication_factors = [1, 2]

    print("==================================================")
    print("       AirStore Performance Benchmark Suite       ")
    print("==================================================")

    process = psutil.Process(os.getpid())
    results = []

    # Temporary directory for benchmark
    tmp_dir = Path(f"data/benchmark_scratch_{os.getpid()}")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Setup Manager + Storage Nodes
    mgr_port = get_free_port()
    mgr_app = create_manager_app(db_path=tmp_dir / "bench_mgr.db", start_monitor=False)
    mgr_srv = ServerThread(mgr_app, "127.0.0.1", mgr_port)
    mgr_srv.start()
    time.sleep(1.0)
    mgr_url = f"http://127.0.0.1:{mgr_port}"

    from datetime import datetime, timezone
    from airstore.core.models import NodeModel

    nodes = []
    node_servers = []
    for i in range(num_nodes):
        node_id = f"bench_node_{i+1}"
        port = get_free_port()
        n_app = create_node_app(
            node_id=node_id,
            storage_dir=tmp_dir / node_id,
            manager_url=mgr_url,
            host="127.0.0.1",
            port=port,
            auto_register=False
        )
        srv = ServerThread(n_app, "127.0.0.1", port)
        srv.start()
        node_servers.append(srv)
        nodes.append(node_id)

        # Register node in DB directly to ensure 100% deterministic startup
        node_model = NodeModel(
            node_id=node_id,
            hostname=socket.gethostname(),
            ip="127.0.0.1",
            port=port,
            total_storage=100 * 1024 * 1024 * 1024,
            available_storage=100 * 1024 * 1024 * 1024,
            status=NodeStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc)
        )
        mgr_app.state.db.register_or_update_node(node_model)

    time.sleep(1.0)
    db = mgr_app.state.db

    storage_svc = mgr_app.state.storage_service
    recovery_svc = mgr_app.state.recovery_service

    try:
        for it in range(iterations):
            for size_mb in file_sizes_mb:
                for chunk_kb in chunk_sizes_kb:
                    for repl in replication_factors:
                        if repl > num_nodes:
                            continue  # Skip replication higher than available node count
                        
                        print(f"[*] Running Benchmark [Iter {it+1}] -> Nodes: {num_nodes} | Size: {size_mb}MB | Chunk: {chunk_kb}KB | Repl: {repl}x ...", flush=True)

                        chunk_bytes = chunk_kb * 1024
                        file_bytes = size_mb * 1024 * 1024
                        
                        # Create test file
                        test_file = tmp_dir / f"test_{size_mb}MB.bin"
                        if not test_file.exists() or test_file.stat().st_size != file_bytes:
                            test_file.write_bytes(os.urandom(file_bytes))

                        orig_hash = calculate_file_hash(test_file)

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
                        dl_file = tmp_dir / f"dl_{size_mb}MB_it{it}.bin"
                        t1 = time.time()
                        storage_svc.stream_file_reconstruction(uploaded.file_id, dl_file)
                        t_download = time.time() - t1
                        download_mbps = round(size_mb / max(t_download, 0.001), 2)

                        # Verify Hash Integrity
                        rec_hash = calculate_file_hash(dl_file)
                        integrity_pass = (orig_hash == rec_hash)

                        cpu_after = process.cpu_percent()
                        mem_after = process.memory_info().rss / (1024 * 1024)

                        row = {
                            "iteration": it + 1,
                            "num_nodes": num_nodes,
                            "file_size_mb": size_mb,
                            "chunk_size_kb": chunk_kb,
                            "replication_factor": repl,
                            "upload_time_sec": round(t_upload, 3),
                            "upload_throughput_mbps": upload_mbps,
                            "download_time_sec": round(t_download, 3),
                            "download_throughput_mbps": download_mbps,
                            "recovery_time_sec": 0.0,
                            "mem_usage_mb": round(mem_after, 2),
                            "integrity_pass": integrity_pass
                        }
                        results.append(row)

                        print(f"    Upload: {upload_mbps} MB/s | Download: {download_mbps} MB/s | Integrity: {'PASS' if integrity_pass else 'FAIL'}", flush=True)

        # Dedicated recovery test at the end of benchmark suite
        if num_nodes >= 2:
            target_node = nodes[0]
            replicas = db.get_replicas_for_node(target_node)
            if replicas:
                t2 = time.time()
                rec_res = recovery_svc.recover_node_failure(target_node)
                t_recovery = round(time.time() - t2, 3)
                print(f"[*] Recovery Benchmark -> Failed Node: {target_node} | Replicas: {len(replicas)} | Time: {t_recovery}s")
                for r in results:
                    if r["replication_factor"] >= 2:
                        r["recovery_time_sec"] = t_recovery
                db.update_node_status(target_node, NodeStatus.ONLINE)

        # Write CSV
        if results:
            output_csv.parent.mkdir(parents=True, exist_ok=True)
            with open(output_csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)

            # Write JSON
            output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(output_json, "w") as f:
                json.dump(results, f, indent=2)

            print(f"\n[+] Benchmark suite completed! Reports saved to '{output_csv.resolve()}' and '{output_json.resolve()}'\n")

    finally:
        for srv in node_servers:
            srv.stop()
        mgr_srv.stop()
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AirStore Benchmark Suite")
    parser.add_argument("--output-csv", type=Path, default=Path("benchmark_results.csv"))
    parser.add_argument("--output-json", type=Path, default=Path("research/results/raw/matrix_results.json"))
    parser.add_argument("--nodes", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--file-sizes", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[256, 512, 1024])
    parser.add_argument("--replication-factors", type=int, nargs="+", default=[1, 2])

    args = parser.parse_args()
    run_benchmark(
        output_csv=args.output_csv,
        output_json=args.output_json,
        num_nodes=args.nodes,
        iterations=args.iterations,
        file_sizes_mb=args.file_sizes,
        chunk_sizes_kb=args.chunk_sizes,
        replication_factors=args.replication_factors
    )

