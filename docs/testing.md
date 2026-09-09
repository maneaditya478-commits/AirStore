# AirStore Testing Guide

AirStore includes a comprehensive test suite built with `pytest`.

## Running Tests

```bash
# Run all unit and integration tests
pytest tests/

# Run core foundation tests
pytest tests/test_core.py

# Run storage node REST API tests
pytest tests/test_storage_node.py

# Run manager database and API tests
pytest tests/test_manager.py

# Run node failure recovery tests
pytest tests/test_recovery.py

# Run full end-to-end multi-node final acceptance test
pytest tests/test_e2e.py
```

## Benchmarking

Run performance benchmarks across file sizes, chunk sizes, and replication factors:

```bash
python scripts/benchmark.py
```
Output results are exported to `benchmark_results.csv`.
