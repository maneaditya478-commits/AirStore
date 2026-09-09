# AirStore Real-LAN Validation & Operational Testing Guide

This guide details the procedure for validating AirStore across multiple physical computers on a local area network (LAN) without Internet access.

## 1. Network Setup & Prerequisites
- Minimum 2 physical computers on the same physical LAN (Ethernet or Wi-Fi).
- Obtain IP addresses (e.g. `192.168.1.10` for Manager, `192.168.1.11` & `192.168.1.12` for Nodes).
- Firewall inbound ports: `8000` (Manager), `8001+` (Nodes).

## 2. Startup Commands

### Machine A (Manager Node)
```bash
python -m airstore.cli.main manager start --host 0.0.0.0 --port 8000
```

### Machine B (Storage Node 1)
```bash
python -m airstore.cli.main node start --id Node_B --host 0.0.0.0 --port 8001 --manager-url http://192.168.1.10:8000
```

### Machine C (Storage Node 2)
```bash
python -m airstore.cli.main node start --id Node_C --host 0.0.0.0 --port 8001 --manager-url http://192.168.1.10:8000
```

## 3. LAN Test Script Execution

Run the automated LAN validation tool from Machine A:

```bash
python -m scripts.lan_test --manager http://192.168.1.10:8000
```

This outputs:
- `research/results/lan_test_results.json` (Structured JSON metrics)
- `research/results/lan_test_report.txt` (Human-readable report)
