# AirStore 🌐🔒
### Offline Distributed File Storage Network for Private LANs

**AirStore** is a private, zero-internet-dependency distributed file-storage system where multiple computers on the same local network (Ethernet LAN, Wi-Fi LAN, Wi-Fi Direct) cooperate to store, replicate, verify, and recover files.

---

## 🌟 Key Features

- 🚫 **100% Offline**: Zero dependencies on Internet, AWS, Firebase, CDNs, or cloud APIs.
- 🧩 **Streaming File Chunking**: Memory-efficient streaming chunker (default 64MB chunks) supporting multi-gigabyte files.
- 🛡️ **Cryptographic Integrity**: Streaming **SHA-256** checksum verification on every chunk and full reconstructed file.
- 🔐 **Authenticated AES-GCM Encryption**: Optional 256-bit AES-GCM encryption for stored chunk payloads.
- 🔄 **Fault Tolerance & Auto-Recovery**: Configurable replication factor (default 2x). Automatically detects node failure via heartbeats and re-replicates data from surviving replicas.
- 📊 **Real-Time Web Dashboard**: Interactive HTML/CSS/JS web dashboard monitoring storage capacity, node statuses, live transfer speeds, chunk placement maps, and event logs.
- 💻 **AirStore CLI**: Comprehensive command-line interface (`airstore upload`, `download`, `nodes`, `status`, `recover`, `verify`).
- 🐳 **Docker Ready**: `docker-compose.yml` for multi-node local cluster orchestration.

---

## 🏗️ Architecture

```
                    USER / CLIENT
                          |
                          v
            +---------------------------+
            |  AirStore Web UI & CLI   |
            +-------------+-------------+
                          |
                          v
            +---------------------------+
            |      Storage Manager      | (Controller & Metadata DB)
            +-------------+-------------+
                          |
      +-------------------+-------------------+
      |                   |                   |
      v                   v                   v
 +----------+        +----------+        +----------+
 | Node A   |        | Node B   |        | Node C   | (Storage Nodes)
 +----------+        +----------+        +----------+
```

---

## 🚀 Quickstart Guide

### 1. Installation

```bash
git clone https://github.com/airstore/airstore.git
cd airstore
pip install -r requirements.txt
```

### 2. Start Manager Node

```bash
python -m airstore.cli.main manager start --host 127.0.0.1 --port 8000
```
Open your browser at `http://127.0.0.1:8000` to view the **AirStore Dashboard**.

### 3. Start Storage Nodes

In separate terminals, start storage nodes:

```bash
# Start Node A
python -m airstore.cli.main node start --id Node_A --port 8001

# Start Node B
python -m airstore.cli.main node start --id Node_B --port 8002

# Start Node C
python -m airstore.cli.main node start --id Node_C --port 8003
```

---

## 💻 CLI Commands

```bash
# Upload a file
python -m airstore.cli.main upload research_dataset.zip --chunk-size 67108864 --replication 2

# Check cluster status
python -m airstore.cli.main status

# List storage nodes
python -m airstore.cli.main nodes

# List stored files
python -m airstore.cli.main files

# Download & reconstruct file
python -m airstore.cli.main download <FILE_ID> --output dataset.zip

# Verify SHA-256 integrity
python -m airstore.cli.main verify dataset.zip

# Simulate node failure recovery
python -m airstore.cli.main recover Node_B
```

---

## 🧪 Running Tests & Benchmarks

```bash
# Run unit & integration tests
pytest tests/

# Run Final Acceptance E2E Multi-Node Test
pytest tests/test_e2e.py

# Run Performance Benchmarks
python scripts/benchmark.py
```

---

## 🐳 Docker Deployment

```bash
docker-compose up --build
```
This starts 1 Manager Node and 3 Storage Nodes in isolated containers connected on a virtual LAN network.

---

## 🔮 Future Research Roadmap

- **Air-Fiber Network Abstraction Layer**: Decoupling socket transport for high-speed laser, FSO, and mmWave point-to-point wireless hardware links.
- **AI Placement Engine (`AIPlacementStrategy`)**: Extension point in `placement.py` for machine-learning-driven chunk placement based on latency, energy, and historical node reliability.
