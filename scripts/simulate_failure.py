import sys
import argparse
import httpx
from airstore.core.config import settings

def simulate_node_failure(manager_url: str, node_id: str):
    """
    Simulate a node failure by invoking the manager recovery endpoint for the specified node.
    """
    url = f"{manager_url.rstrip('/')}/api/nodes/{node_id}/recover"
    print(f"[*] Simulating node failure for '{node_id}' via Manager API ({url})...")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[+] Failure simulated successfully! Recovery status: {data}")
            else:
                print(f"[-] Manager API returned error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[-] Failed to communicate with Manager API: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AirStore Node Failure Simulator")
    parser.add_argument("--node", required=True, help="Target Node ID to simulate failure on")
    parser.add_argument("--manager", default=f"http://{settings.MANAGER_HOST}:{settings.MANAGER_PORT}", help="Manager API URL")
    
    args = parser.parse_args()
    simulate_node_failure(args.manager, args.node)
