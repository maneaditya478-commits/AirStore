# AirStore Fault Injection & Resilience Testing

This document describes the controlled fault injection tool (`scripts/inject_failure.py`) used to test network resilience, node death, and recovery.

## 1. Supported Scenarios

| Scenario | Command | Action |
|----------|---------|--------|
| **Node Kill / Crash** | `python -m scripts.inject_failure --action kill --node Node_B` | Flags node OFFLINE and triggers instant re-replication of missing replicas. |
| **Node Return** | `python -m scripts.inject_failure --action restore --node Node_B` | Triggers returning node metadata reconciliation (`reconcile_returning_node`). |
| **Chunk Corruption** | `python -m scripts.inject_failure --action corrupt --node Node_B --chunk <chunk_id>` | Modifies chunk byte on disk to trigger SHA-256 integrity verification failure. |

## 2. Metric Collection
For every failure experiment, AirStore automatically records:
- **Failure Detection Time (FDT)**: Time elapsed until heartbeat timeout marks node OFFLINE.
- **Recovery Start Time (RST)**: Time elapsed from detection to recovery loop start.
- **Recovery Completion Time (RCT)**: Duration required to re-replicate missing chunks onto healthy target nodes.
- **Total Recovery Time**: $T_{recovery} = T_{detection} + T_{execution}$.
