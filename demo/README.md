---
title: AirStore v1.1.0 Demo
emoji: 🗄️
colorFrom: blue
colorTo: purple
sdk: static
pinned: false
---

# AirStore v1.1.0 — Interactive Distributed Storage Demo

Interactive static demonstration of **AirStore v1.1.0**, an offline distributed file-storage system for local area networks (LAN).

## 🚀 Overview

AirStore is a resilient, offline distributed storage system designed to chunk, replicate, verify, and recover data across local storage nodes without internet or cloud dependencies.

- **Offline LAN Architecture**: Operates on private local networks.
- **Configurable Replication**: Multi-replica fault tolerance.
- **SHA-256 Data Integrity**: End-to-end checksum verification.
- **Automatic Self-Healing**: Detects node failure and rebuilds missing chunks from surviving replicas.
- **Resumable & Concurrent**: Efficient chunk streaming with bandwidth optimization.

---

## 🛠️ Architecture

- **Client / REST API**: High-performance HTTP interfaces.
- **Manager Node**: SQLite WAL metadata catalog, node health monitor, rule-based placement engine, and recovery orchestrator.
- **Storage Nodes**: Decoupled worker daemons handling local chunk storage and inter-node replication.

---

## 🧪 Interactive Simulator Features

This Hugging Face Space provides a client-side visualization of AirStore operations:

1. **File Chunking Pipeline**: Upload any local file (100% browser-side privacy) to observe chunking, placement, and SHA-256 verification.
2. **Browser SHA-256 Computation**: Calculates real cryptographic digests using Web Crypto API.
3. **Dynamic Cluster Configuration**: Adjust active storage nodes (1–6) and replication factors (1–3).
4. **Fault-Tolerance Injection**: Simulate node failures or chunk corruptions to watch automatic healing in real time.
5. **Resumable Upload Demo**: Visualize bandwidth savings when resuming interrupted file transfers.

---

## 📊 Research Evaluation & Results

- **Automated Unit & E2E Tests**: 27/27 PASS
- **Executed Fault Runs**: 30 (Scenarios F1, F3, F5, F8, F9, F10 with 5 repetitions each)
- **Executed Success Rate**: 100%
- **SHA-256 Integrity Rate**: 100%
- **Research Figures**: 9 rendered plots

---

## ⚠️ Current System Limitations

- Scenarios F2, F4, F6, and F7 were not experimentally executed due to OS/Hardware injection requirements.
- Manager metadata uses SQLite WAL (single-writer model suited for small/medium LAN clusters).
- Erasure coding implementation ($K=4, M=2$) remains experimental.
- This Hugging Face Space is a static client-side simulation and does not connect to a live backend.

---

## 🔗 Repository & Source Code

- **GitHub Repository**: [https://github.com/maneaditya478-commits/AirStore](https://github.com/maneaditya478-commits/AirStore)
- **License**: MIT
