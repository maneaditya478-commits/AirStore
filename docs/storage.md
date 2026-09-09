# AirStore Storage Engine & Placement Specification

## 1. Streaming Chunking Engine
- Default chunk size: **64 MB** (configurable via `--chunk-size` or `AIRSTORE_CHUNK_SIZE`).
- Uses streaming reads and writes (`FileChunker`) to process multi-gigabyte files (e.g. 10 GB+) within a fixed memory footprint.

## 2. Metadata Database Schema (SQLite)
- `nodes`: Node identity, IP, port, storage stats, health status, last heartbeat.
- `files`: File identity, filename, total size, created date, overall SHA-256 hash, status.
- `chunks`: Chunk identity, sequence number, size, chunk SHA-256 hash.
- `chunk_replicas`: Chunk ID, node ID, replica number, status (`STORED`, `MISSING`, `CORRUPTED`).
- `transfers`: Upload/download transfer status, progress percentage, speed (MB/s).
- `events`: System audit log.

## 3. Placement Engine (`placement.py`)
- Strategy pattern (`PlacementStrategy`).
- Implemented `RuleBasedPlacementStrategy` balances storage load across online nodes while ensuring no single node hosts multiple replicas of the same chunk.
- Extension point `AIPlacementStrategy` provided for future machine-learning-based placement models.
