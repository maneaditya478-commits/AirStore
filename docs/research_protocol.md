# AirStore Research Protocol & Experiment Methodology

This protocol defines the standardized schema and methodology for conducting reproducible distributed storage experiments in AirStore v1.1.

## 1. Experiment Schema (`research/results/benchmark_results.csv`)

| Field Name | Type | Description |
|------------|------|-------------|
| `experiment_id` | String | Unique UUID for the benchmark iteration |
| `timestamp` | String | ISO 8601 UTC timestamp |
| `system_version` | String | AirStore software version (e.g. `v1.1.0-dev`) |
| `node_count` | Integer | Total active storage nodes in cluster |
| `chunk_size_mb` | Integer | Size of individual file chunks in MB |
| `replication_factor` | Integer | Target replica count per chunk |
| `file_size_mb` | Integer | Total size of uploaded/downloaded file in MB |
| `operation` | String | `UPLOAD`, `DOWNLOAD`, or `RECOVERY` |
| `duration_seconds` | Float | Measured execution time in seconds |
| `throughput_mbps` | Float | Measured data transfer rate in MB/s |
| `cpu_percent` | Float | Average process CPU utilization % |
| `memory_mb` | Float | Peak process RSS memory usage in MB |
| `integrity_verified` | Boolean | True if overall SHA-256 matches expected |
| `result` | String | `PASS` or `FAIL` |

## 2. Statistical Repeatability Protocol
- All performance matrix combinations are executed for a minimum of **5 repetitions**.
- Results are analyzed using `scripts/analyze_results.py` to calculate:
  - **Mean** ($\mu$)
  - **Median** ($M$)
  - **Minimum** ($min$)
  - **Maximum** ($max$)
  - **Standard Deviation** ($\sigma$)
