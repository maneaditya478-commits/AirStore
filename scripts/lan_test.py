import os
import sys
import time
import math
import json
import argparse
import httpx
from pathlib import Path
from airstore.core.config import settings
from airstore.core.hashing import calculate_file_hash

def run_lan_validation(manager_url: str, output_dir: Path = Path("research/results")):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_out = output_dir / "lan_test_results.json"
    txt_out = output_dir / "lan_test_report.txt"

    url_base = manager_url.rstrip('/')
    print(f"[*] AirStore Real-LAN Validation Tool starting against {url_base}...")

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manager_url": manager_url,
        "nodes": [],
        "upload_test": {},
        "download_test": {},
        "recovery_test": {},
        "integrity_verified": False,
        "status": "FAILED"
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            # 1. Fetch Node Info
            resp = client.get(f"{url_base}/api/nodes")
            resp.raise_for_status()
            nodes = resp.json()
            results["nodes"] = nodes
            print(f"[+] Discovered {len(nodes)} cluster nodes.")

            if not nodes:
                print("[-] Error: No storage nodes registered with manager.")
                return

            # 2. Upload Test (5MB payload)
            temp_file = Path("data/lan_test_5mb.bin")
            temp_file.parent.mkdir(parents=True, exist_ok=True)
            data = os.urandom(5 * 1024 * 1024)
            temp_file.write_bytes(data)
            orig_hash = calculate_file_hash(temp_file)

            print("[*] Uploading 5MB test file...")
            t0 = time.time()
            with open(temp_file, "rb") as f:
                up_resp = client.post(
                    f"{url_base}/api/files/upload",
                    files={"file": (temp_file.name, f)},
                    data={"chunk_size": "524288", "replication_factor": "2"}
                )
                up_resp.raise_for_status()
                file_info = up_resp.json()
            up_time = time.time() - t0
            up_speed = round(5.0 / max(up_time, 0.001), 2)

            results["upload_test"] = {
                "file_id": file_info["file_id"],
                "size_bytes": file_info["size"],
                "duration_sec": round(up_time, 3),
                "speed_mbps": up_speed,
                "chunks": math.ceil(file_info["size"] / 524288)
            }
            print(f"[+] Upload complete: {up_speed} MB/s in {round(up_time, 2)}s")

            # 3. Download Test
            dl_file = Path("data/lan_download_5mb.bin")
            print("[*] Downloading & reconstructing file...")
            t1 = time.time()
            with client.stream("GET", f"{url_base}/api/files/{file_info['file_id']}/download") as stream_resp:
                stream_resp.raise_for_status()
                with open(dl_file, "wb") as out_f:
                    for chunk in stream_resp.iter_bytes():
                        out_f.write(chunk)
            dl_time = time.time() - t1
            dl_speed = round(5.0 / max(dl_time, 0.001), 2)
            dl_hash = calculate_file_hash(dl_file)

            results["download_test"] = {
                "duration_sec": round(dl_time, 3),
                "speed_mbps": dl_speed,
                "sha256_match": dl_hash == orig_hash
            }
            print(f"[+] Download complete: {dl_speed} MB/s | SHA-256 Match: {dl_hash == orig_hash}")

            # 4. Failure Recovery Test (if >= 2 nodes)
            if len(nodes) >= 2:
                target_node = nodes[0]["node_id"]
                print(f"[*] Simulating failure on node '{target_node}'...")
                t2 = time.time()
                rec_resp = client.post(f"{url_base}/api/nodes/{target_node}/recover")
                rec_time = time.time() - t2
                rec_data = rec_resp.json() if rec_resp.status_code == 200 else {}

                results["recovery_test"] = {
                    "target_node": target_node,
                    "duration_sec": round(rec_time, 3),
                    "status": rec_data.get("status", "FAILED"),
                    "recovered_chunks": rec_data.get("recovered_chunks", 0)
                }
                print(f"[+] Recovery complete in {round(rec_time, 2)}s: {rec_data}")

            results["integrity_verified"] = dl_hash == orig_hash
            results["status"] = "PASS" if dl_hash == orig_hash else "FAILED"

    except Exception as e:
        print(f"[-] LAN Validation error: {e}")
        results["error"] = str(e)

    # Save JSON results
    with open(json_out, "w") as f:
        json.dump(results, f, indent=2)

    # Save human-readable text report
    with open(txt_out, "w") as f:
        f.write("==================================================\n")
        f.write("       AirStore Real-LAN Validation Report        \n")
        f.write("==================================================\n\n")
        f.write(f"Timestamp:          {results['timestamp']}\n")
        f.write(f"Manager URL:        {results['manager_url']}\n")
        f.write(f"Status:             {results['status']}\n")
        f.write(f"Discovered Nodes:   {len(results['nodes'])}\n\n")
        f.write("--- Upload Performance ---\n")
        f.write(f"Throughput:         {results['upload_test'].get('speed_mbps', 0)} MB/s\n")
        f.write(f"Duration:           {results['upload_test'].get('duration_sec', 0)} s\n\n")
        f.write("--- Download Performance ---\n")
        f.write(f"Throughput:         {results['download_test'].get('speed_mbps', 0)} MB/s\n")
        f.write(f"SHA-256 Match:      {results['download_test'].get('sha256_match', False)}\n\n")
        f.write("==================================================\n")

    print(f"[+] LAN Validation finished! Reports saved to {output_dir.resolve()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AirStore LAN Validation Script")
    parser.add_argument("--manager", default=f"http://{settings.MANAGER_HOST}:{settings.MANAGER_PORT}")
    args = parser.parse_args()
    run_lan_validation(args.manager)
