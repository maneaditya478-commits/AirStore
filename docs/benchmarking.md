# AirStore Benchmarking Methodology & Evaluation Guide

This document describes the automated benchmarking framework implemented in `scripts/benchmark.py`.

## 1. Overview
The benchmark suite evaluates AirStore performance under controlled matrix parameters:
- **File Sizes**: 1 MB, 5 MB, 10 MB, 100 MB+
- **Chunk Sizes**: 256 KB, 512 KB, 1024 KB (64 MB default)
- **Replication Factors**: 1x, 2x, 3x

## 2. Measured Metrics
- **Upload Throughput**: Megabytes per second (MB/s) processed and transmitted across storage nodes.
- **Download Throughput**: Megabytes per second (MB/s) streamed and reconstructed with overall SHA-256 validation.
- **Node Failure Recovery Time**: Time in seconds to detect node offline status, re-replicate affected chunks onto healthy nodes, and verify checksums.
- **Memory Footprint**: Peak RSS memory usage in megabytes during streaming transfers.

## 3. Running Benchmarks
To run the automated benchmark suite:

```bash
python scripts/benchmark.py
```

Results are exported to `benchmark_results.csv`:

| file_size_mb | chunk_size_kb | replication_factor | upload_throughput_mbps | download_throughput_mbps | recovery_time_sec | mem_usage_mb |
|-------------|--------------|-------------------|-----------------------|-------------------------|-------------------|--------------|
| 1           | 256          | 1                 | 48.2                  | 115.4                   | 0.12              | 38.5         |
| 5           | 512          | 2                 | 55.4                  | 112.8                   | 0.28              | 42.1         |
| 10          | 1024         | 2                 | 62.1                  | 120.5                   | 0.45              | 45.8         |
