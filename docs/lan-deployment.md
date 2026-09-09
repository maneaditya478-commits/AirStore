# AirStore LAN Deployment & Multi-Machine Setup Guide

AirStore supports deploying Manager and Storage Nodes across multiple physical computers connected on the same local network (Ethernet LAN, Wi-Fi, or Wi-Fi Direct).

## 1. Network Requirements
- All machines must be connected to the same subnet/LAN.
- Inbound TCP ports must be allowed through local OS firewalls:
  - **Manager Node**: Port `8000` (default)
  - **Storage Nodes**: Ports `8001`, `8002`, `8003`, etc.

## 2. Deploying Manager Node on Machine A (e.g. IP `192.168.1.100`)

To allow remote storage nodes on the LAN to register with the Manager, bind the Manager to `0.0.0.0`:

```bash
python -m airstore.cli.main manager start --host 0.0.0.0 --port 8000
```
Or configure via environment variables in `.env`:
```ini
AIRSTORE_MANAGER_HOST=0.0.0.0
AIRSTORE_MANAGER_PORT=8000
```

## 3. Deploying Storage Nodes on Machine B (e.g. IP `192.168.1.105`)

Start a Storage Node on Machine B, pointing `--manager-url` to Machine A's LAN IP:

```bash
python -m airstore.cli.main node start --id Node_B --host 0.0.0.0 --port 8001 --manager-url http://192.168.1.100:8000
```

AirStore automatically detects Machine B's LAN IP (`192.168.1.105`) and advertises it to the Manager Node so chunk transfers can occur seamlessly across machines.

## 4. Localhost Development Mode (Single Machine)

When testing on a single development machine, use `127.0.0.1`:

```bash
# Terminal 1 - Manager
python -m airstore.cli.main manager start --host 127.0.0.1 --port 8000

# Terminal 2 - Node 1
python -m airstore.cli.main node start --id Node_1 --port 8001

# Terminal 3 - Node 2
python -m airstore.cli.main node start --id Node_2 --port 8002
```
