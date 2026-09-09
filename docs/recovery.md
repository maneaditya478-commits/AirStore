# AirStore Failure Detection & Recovery Architecture

## 1. Failure Detection
1. Storage nodes send periodic heartbeats (`POST /api/nodes/heartbeat`) every `AIRSTORE_HEARTBEAT_INTERVAL` seconds.
2. The Manager Node runs a background `HeartbeatMonitor` thread checking `last_heartbeat` timestamps.
3. If a node fails to send heartbeats for longer than `AIRSTORE_HEARTBEAT_TIMEOUT` (15s), the node is marked `OFFLINE`.

## 2. Automatic Data Recovery Workflow

```
[ Node Death Detected ]
          |
          v
[ Identify Affected Chunk Replicas ]
          |
          v
[ Mark Node Replicas as MISSING ]
          |
          v
[ For Each Affected Chunk: ]
          |
    +-----+--------------------------------+
    |                                      |
(Surviving Replicas Found)        (No Surviving Replicas)
    |                                      |
    v                                      v
[ Select Replacement Node ]       [ Mark File CORRUPTED ]
    |                                      |
    v                                      v
[ Instruct Re-Replication ]       [ Log RECOVERY_FAILED ]
    |
    v
[ Verify SHA-256 Checksum ]
    |
    v
[ Update Replica Metadata ]
```

## 3. Guarantees
- Re-replication preserves configured replication factor (e.g. 2x) across healthy surviving nodes.
- SHA-256 hashes are verified after chunk copying before marking the new replica `STORED`.
