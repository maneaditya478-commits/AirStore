# AirStore Architecture Specification

## 1. High-Level System Overview

AirStore is an offline, zero-internet-dependency distributed file-storage system designed for private local area networks (Ethernet, Wi-Fi LAN, Wi-Fi Direct, and future point-to-point wireless media).

```
                      USER / CLIENT
                            |
                            v
                    +---------------+
                    |  AirStore UI  |  (Single-Page Web Dashboard & CLI)
                    +-------+-------+
                            |
                            v
                    +---------------+
                    | Storage       |  (Controller / Manager Node)
                    | Manager       |  (Metadata DB, Heartbeats, Recovery)
                    +-------+-------+
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
   +----------+        +----------+        +----------+
   | Storage  |        | Storage  |        | Storage  |
   | Node A   |        | Node B   |        | Node C   |
   +----------+        +----------+        +----------+
```

## 2. Component Breakdown

### A. Manager Node (Controller)
- **Node Registry**: Tracks registered storage nodes, hostnames, IP addresses, ports, and storage statistics.
- **Metadata Database**: SQLite WAL-mode database maintaining transactional state for files, chunks, chunk replicas, active transfers, and event logs.
- **Placement Engine**: Pluggable placement strategy (`PlacementStrategy` interface). Implemented with `RuleBasedPlacementStrategy` (capacity & load balancing) and an extension point for `AIPlacementStrategy`.
- **Heartbeat & Failure Detector**: Periodic background thread monitoring node heartbeats and triggering automatic recovery when heartbeats time out.
- **REST API & Web Dashboard**: Exposes management APIs and serves the offline frontend UI.

### B. Storage Nodes
- Lightweight FastAPI microservices running on participating network nodes.
- Manage chunk storage on local disk.
- Compute and verify SHA-256 cryptographic hashes for received chunks.
- Support peer-to-peer chunk replication requests (`POST /replicate`).
- Periodically broadcast heartbeats to Manager Node.

## 3. Network & Offline Guarantee
- Completely zero external internet dependency (no cloud APIs, CDNs, or online authentication).
- Communicates purely over HTTP/REST on local network interfaces.
