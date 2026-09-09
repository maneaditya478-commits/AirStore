import os
import sys
import argparse
import uvicorn
import httpx
from pathlib import Path
from airstore.core.config import settings
from airstore.core.hashing import calculate_file_hash

DEFAULT_MANAGER_URL = f"http://{settings.MANAGER_HOST}:{settings.MANAGER_PORT}"

def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def cmd_manager_start(args):
    """Start the AirStore Manager Node."""
    print(f"[*] Starting AirStore Manager Node on {args.host}:{args.port}...")
    from airstore.manager.main import create_manager_app
    app = create_manager_app(db_path=Path(args.db) if args.db else None)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

def cmd_node_start(args):
    """Start an AirStore Storage Node."""
    storage_dir = Path(args.storage_dir) if args.storage_dir else settings.NODE_STORAGE_DIR / args.id
    print(f"[*] Starting AirStore Storage Node '{args.id}' on {args.host}:{args.port}...")
    print(f"[*] Data directory: {storage_dir.resolve()}")
    from airstore.node.main import create_node_app
    app = create_node_app(
        node_id=args.id,
        storage_dir=storage_dir,
        manager_url=args.manager_url,
        host=args.host,
        port=args.port
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

def cmd_upload(args):
    """Upload a file to the AirStore network."""
    path = Path(args.filepath).resolve()
    if not path.exists():
        print(f"[-] Error: File not found at {path}")
        sys.exit(1)

    url = f"{args.manager_url.rstrip('/')}/api/files/upload"
    print(f"[*] Uploading file '{path.name}' ({format_bytes(path.stat().st_size)}) to AirStore...")

    try:
        with open(path, "rb") as f:
            files = {"file": (path.name, f)}
            data = {
                "chunk_size": str(args.chunk_size),
                "replication_factor": str(args.replication)
            }
            with httpx.Client(timeout=600.0) as client:
                resp = client.post(url, files=files, data=data)
                resp.raise_for_status()
                res = resp.json()
                print(f"[+] SUCCESS! File uploaded successfully.")
                print(f"    File ID:     {res['file_id']}")
                print(f"    Filename:    {res['filename']}")
                print(f"    Size:        {format_bytes(res['size'])}")
                print(f"    SHA-256:     {res['overall_hash']}")
                print(f"    Replicas:    {res['replication_factor']}")
    except Exception as e:
        print(f"[-] Upload failed: {e}")
        sys.exit(1)

def cmd_download(args):
    """Download and reconstruct a file from AirStore."""
    url = f"{args.manager_url.rstrip('/')}/api/files/{args.file_id}/download"
    print(f"[*] Requesting reconstruction of file ID '{args.file_id}'...")

    try:
        with httpx.Client(timeout=600.0) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                cd = resp.headers.get("content-disposition", "")
                filename = "downloaded_file"
                if "filename=" in cd:
                    filename = cd.split("filename=")[-1].strip('"')
                
                output_path = Path(args.output) if args.output else Path.cwd() / filename
                print(f"[*] Streaming reconstructed bytes to {output_path}...")
                
                with open(output_path, "wb") as out_f:
                    for chunk in resp.iter_bytes(chunk_size=64*1024):
                        out_f.write(chunk)

                print(f"[+] SUCCESS! File downloaded and reconstructed at {output_path.resolve()}")
                print(f"    Reconstructed SHA-256: {calculate_file_hash(output_path)}")

    except Exception as e:
        print(f"[-] Download failed: {e}")
        sys.exit(1)

def cmd_nodes(args):
    """List storage nodes and their statuses."""
    url = f"{args.manager_url.rstrip('/')}/api/nodes"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            nodes = resp.json()

            print("\n=== AirStore Node Registry ===")
            print(f"{'Node ID':<15} {'Status':<10} {'Host/IP':<20} {'Port':<6} {'Available Storage':<18} {'Total Storage':<18}")
            print("-" * 85)
            for n in nodes:
                print(f"{n['node_id']:<15} {n['status']:<10} {n['ip']:<20} {n['port']:<6} {format_bytes(n['available_storage']):<18} {format_bytes(n['total_storage']):<18}")
            print()
    except Exception as e:
        print(f"[-] Failed to fetch nodes: {e}")

def cmd_files(args):
    """List stored files in AirStore."""
    url = f"{args.manager_url.rstrip('/')}/api/files"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            files = resp.json()

            print("\n=== Stored Files ===")
            print(f"{'File ID':<38} {'Filename':<25} {'Size':<12} {'Status':<10} {'Created At':<22}")
            print("-" * 110)
            for f in files:
                print(f"{f['file_id']:<38} {f['filename']:<25} {format_bytes(f['size']):<12} {f['status']:<10} {f['created_at'][:19]:<22}")
            print()
    except Exception as e:
        print(f"[-] Failed to fetch files: {e}")

def cmd_status(args):
    """Get overall cluster status."""
    url = f"{args.manager_url.rstrip('/')}/api/stats"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            st = resp.json()

            print("\n=== AirStore Cluster Status ===")
            print(f"  Total Nodes:       {st['total_nodes']} (Online: {st['online_nodes']}, Offline: {st['offline_nodes']})")
            print(f"  Total Files:       {st['total_files']}")
            print(f"  Total Storage:     {format_bytes(st['total_storage'])}")
            print(f"  Used Storage:      {format_bytes(st['used_storage'])}")
            print(f"  Available Storage: {format_bytes(st['available_storage'])}")
            print(f"  Replication:       {st['replication_factor']}x")
            print()
    except Exception as e:
        print(f"[-] Failed to fetch cluster status: {e}")

def cmd_recover(args):
    """Trigger manual node failure recovery."""
    url = f"{args.manager_url.rstrip('/')}/api/nodes/{args.node_id}/recover"
    print(f"[*] Initiating failure recovery for node '{args.node_id}'...")
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url)
            resp.raise_for_status()
            res = resp.json()
            print(f"[+] Recovery finished!")
            print(f"    Status:           {res.get('status')}")
            print(f"    Recovered Chunks: {res.get('recovered_chunks')}")
            print(f"    Failed Chunks:    {res.get('failed_chunks')}")
    except Exception as e:
        print(f"[-] Recovery trigger failed: {e}")

def cmd_verify(args):
    """Verify file integrity hash."""
    path_or_id = args.target
    p = Path(path_or_id)
    if p.exists():
        file_hash = calculate_file_hash(p)
        print(f"[*] Local File Path: {p.resolve()}")
        print(f"[*] Computed SHA-256: {file_hash}")
    else:
        # Query manager for file ID
        url = f"{args.manager_url.rstrip('/')}/api/files/{path_or_id}"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                detail = resp.json()
                print(f"[*] File ID:        {detail['file']['file_id']}")
                print(f"[*] Filename:       {detail['file']['filename']}")
                print(f"[*] Expected Hash:  {detail['file']['overall_hash']}")
                print(f"[*] Status:         {detail['file']['status']}")
        except Exception as e:
            print(f"[-] Verification query failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="AirStore CLI - Offline Distributed Storage Network")
    parser.add_argument("--manager-url", default=DEFAULT_MANAGER_URL, help="Manager Node API URL")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # manager start
    p_mgr = subparsers.add_parser("manager", help="Manager operations")
    p_mgr_sub = p_mgr.add_subparsers(dest="subcommand", required=True)
    p_mgr_start = p_mgr_sub.add_parser("start", help="Start Manager Node server")
    p_mgr_start.add_argument("--host", default=settings.MANAGER_HOST)
    p_mgr_start.add_argument("--port", type=int, default=settings.MANAGER_PORT)
    p_mgr_start.add_argument("--db", default=None, help="Database path")
    p_mgr_start.set_defaults(func=cmd_manager_start)

    # node start
    p_node = subparsers.add_parser("node", help="Node operations")
    p_node_sub = p_node.add_subparsers(dest="subcommand", required=True)
    p_node_start = p_node_sub.add_parser("start", help="Start Storage Node server")
    p_node_start.add_argument("--id", required=True, help="Storage Node ID")
    p_node_start.add_argument("--host", default="127.0.0.1")
    p_node_start.add_argument("--port", type=int, default=8001)
    p_node_start.add_argument("--storage-dir", default=None)
    p_node_start.add_argument("--manager-url", default=DEFAULT_MANAGER_URL)
    p_node_start.set_defaults(func=cmd_node_start)

    # upload
    p_up = subparsers.add_parser("upload", help="Upload a file to AirStore")
    p_up.add_argument("filepath", help="Path to local file to upload")
    p_up.add_argument("--chunk-size", type=int, default=settings.CHUNK_SIZE, help="Chunk size in bytes")
    p_up.add_argument("--replication", type=int, default=settings.REPLICATION_FACTOR, help="Replication factor")
    p_up.set_defaults(func=cmd_upload)

    # download
    p_dl = subparsers.add_parser("download", help="Download a file from AirStore")
    p_dl.add_argument("file_id", help="ID of file to download")
    p_dl.add_argument("--output", help="Destination file path")
    p_dl.set_defaults(func=cmd_download)

    # nodes
    p_nodes = subparsers.add_parser("nodes", help="List storage nodes")
    p_nodes.set_defaults(func=cmd_nodes)

    # files
    p_files = subparsers.add_parser("files", help="List stored files")
    p_files.set_defaults(func=cmd_files)

    # status
    p_stat = subparsers.add_parser("status", help="Show cluster status")
    p_stat.set_defaults(func=cmd_status)

    # recover
    p_rec = subparsers.add_parser("recover", help="Trigger failure recovery for a node")
    p_rec.add_argument("node_id", help="Failed node ID")
    p_rec.set_defaults(func=cmd_recover)

    # verify
    p_ver = subparsers.add_parser("verify", help="Verify SHA-256 hash of a file or file_id")
    p_ver.add_argument("target", help="Local file path or AirStore File ID")
    p_ver.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)

if __name__ == "__main__":
    main()
