import sys
import argparse
import httpx
from airstore.core.config import settings

def inject_failure(action: str, node_id: str, manager_url: str):
    url_base = manager_url.rstrip('/')
    
    print(f"[*] AirStore Failure Injection Tool -> Action: {action.upper()} | Target Node: {node_id}")

    if action == "kill":
        url = f"{url_base}/api/nodes/{node_id}/recover"
        print(f"[*] Simulating crash of node '{node_id}' and triggering recovery...")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url)
                resp.raise_for_status()
                res = resp.json()
                print(f"[+] Node crash & recovery result: {res}")
        except Exception as e:
            print(f"[-] Failure injection error: {e}")

    elif action == "status":
        url = f"{url_base}/api/stats"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                print(f"[+] Cluster Status: {resp.json()}")
        except Exception as e:
            print(f"[-] Status check error: {e}")

    elif action == "recover":
        url = f"{url_base}/api/nodes/{node_id}/recover"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url)
                resp.raise_for_status()
                print(f"[+] Recovery result: {resp.json()}")
        except Exception as e:
            print(f"[-] Recovery error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AirStore Failure Injection Tool")
    parser.add_argument("--action", choices=["kill", "status", "recover"], default="kill")
    parser.add_argument("--node", default="Node_B", help="Target node ID")
    parser.add_argument("--manager", default=f"http://{settings.MANAGER_HOST}:{settings.MANAGER_PORT}")

    args = parser.parse_args()
    inject_failure(args.action, args.node, args.manager)
