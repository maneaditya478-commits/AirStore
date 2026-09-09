# Fault-Tolerance Analysis

## Experimental Scenarios
Evaluating AirStore under 10 fault scenarios (F1-F10) covering node failures, chunk corruption, returning node reconciliation, resumable uploads, and multi-node crashes.

## Number of Runs
Executed 5 repetitions per automated scenario (total 30 local loopback runs across 6 executed scenarios). 4 hardware/OS-dependent scenarios recorded as `NOT_EXECUTED`.

## Failure Detection
| Exp ID | Scenario Name | Mean Detection Time (s) | Std Dev (s) |
| :--- | :--- | :---: | :---: |
| F1 | Node failure after successful upload | 0.205s | 0.011s |
| F3 | Node failure during download | 0.001s | 0.0s |
| F5 | Stored chunk corruption | 0.001s | 0.0s |
| F8 | Returning node reconciliation | 1.46s | 0.039s |
| F9 | Interrupted transfer / resumable recovery | 5.853s | 0.177s |
| F10 | Multiple-node failure | 2.593s | 1.447s |


## Recovery Performance
| Exp ID | Scenario Name | Mean Recovery Time (s) | Std Dev (s) | Success Rate |
| :--- | :--- | :---: | :---: | :---: |
| F1 | Node failure after successful upload | 2.788s | 0.05s | 100% |
| F3 | Node failure during download | 1.428s | 0.035s | 100% |
| F5 | Stored chunk corruption | 1.08s | 0.022s | 100% |
| F8 | Returning node reconciliation | 1.122s | 0.069s | 100% |
| F9 | Interrupted transfer / resumable recovery | 5.871s | 0.147s | 100% |
| F10 | Multiple-node failure | 2.227s | 1.238s | 100% |


## Integrity Verification
All executed file recovery operations performed end-to-end SHA-256 hash verification. Integrity success rate across executed experiments: **100%**.

## Returning Node Behavior
In Experiment F8, returning nodes were re-registered and missing chunk replicas were reconciled automatically via `reconcile_returning_node()` with zero data corruption.

## Multiple Failure Behavior
In Experiment F10, sequential 2-node failures under 3x replication factor resulted in full replica reconstruction on surviving nodes without data loss.

## Observed Limitations
- F2 (Mid-upload crash) & F4 (Mid-replication interrupt) require external process daemon injection.
- F6 (Network interruption) & F7 (Disk-full condition) require physical LAN disconnection and OS-level volume capacity limits.

## Summary
AirStore demonstrated **100% integrity success rate** and robust recovery performance across all executed fault scenarios.
