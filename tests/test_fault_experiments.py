import os
import json
import pytest
from pathlib import Path
from scripts.run_fault_experiments import not_executed_result
from scripts.analyze_results import (
    calculate_stats, analyze_fault_results_json, generate_dataset_summary, generate_final_data_audit
)
from scripts.generate_research_report import generate_report

def test_fault_experiment_result_schema():
    res = not_executed_result("F6", "Network interruption", "PHYSICAL_LAN_DISCONNECT", "NOT EXECUTED — HARDWARE/LAN REQUIRED")
    expected_keys = [
        "experiment_id", "experiment_name", "timestamp", "system_version",
        "node_count", "chunk_size_mb", "replication_factor", "file_size_mb",
        "network_type", "failure_type", "affected_node", "affected_chunks",
        "failure_injection_time", "failure_detection_time", "recovery_start_time",
        "recovery_completion_time", "detection_time_seconds", "recovery_time_seconds",
        "total_recovery_time_seconds", "integrity_verified", "final_cluster_status",
        "result", "error", "notes"
    ]
    for key in expected_keys:
        assert key in res
    assert res["experiment_id"] == "F6"
    assert res["result"] == "NOT_EXECUTED"
    assert res["integrity_verified"] is None

def test_fault_experiment_serialization(tmp_path):
    res_list = [
        {
            "experiment_id": "F1", "experiment_name": "Node failure after upload",
            "timestamp": "2026-09-09T21:00:00Z", "system_version": "1.1.0",
            "node_count": 3, "chunk_size_mb": 0.5, "replication_factor": 2, "file_size_mb": 2.0,
            "network_type": "LOOPBACK", "failure_type": "NODE_CRASH", "affected_node": "node_A",
            "affected_chunks": 2, "failure_injection_time": 100.0, "failure_detection_time": 100.2,
            "recovery_start_time": 100.2, "recovery_completion_time": 103.0,
            "detection_time_seconds": 0.2, "recovery_time_seconds": 2.8, "total_recovery_time_seconds": 3.0,
            "integrity_verified": True, "final_cluster_status": "HEALTHY",
            "result": "PASS", "error": None, "notes": "Test run 1"
        },
        {
            "experiment_id": "F1", "experiment_name": "Node failure after upload",
            "timestamp": "2026-09-09T21:01:00Z", "system_version": "1.1.0",
            "node_count": 3, "chunk_size_mb": 0.5, "replication_factor": 2, "file_size_mb": 2.0,
            "network_type": "LOOPBACK", "failure_type": "NODE_CRASH", "affected_node": "node_B",
            "affected_chunks": 2, "failure_injection_time": 200.0, "failure_detection_time": 200.2,
            "recovery_start_time": 200.2, "recovery_completion_time": 203.2,
            "detection_time_seconds": 0.2, "recovery_time_seconds": 3.0, "total_recovery_time_seconds": 3.2,
            "integrity_verified": True, "final_cluster_status": "HEALTHY",
            "result": "PASS", "error": None, "notes": "Test run 2"
        }
    ]

    json_path = tmp_path / "test_fault.json"
    with open(json_path, "w") as f:
        json.dump(res_list, f)

    csv_path = tmp_path / "test_fault_summary.csv"
    md_path = tmp_path / "test_fault_analysis.md"
    plots_dir = tmp_path / "plots"

    analyze_fault_results_json(json_path, csv_path, md_path, plots_dir)

    assert csv_path.exists()
    assert md_path.exists()

    with open(csv_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 11  # header + 10 scenario rows (F1-F10)
        assert "F1" in lines[1]

def test_statistical_aggregation_and_missing_values():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    stats = calculate_stats(vals)
    assert stats["mean"] == 3.0
    assert stats["median"] == 3.0
    assert stats["min"] == 1.0
    assert stats["max"] == 5.0
    assert stats["std_dev"] > 0

    empty_stats = calculate_stats([])
    assert empty_stats["mean"] == 0.0
    assert empty_stats["median"] == 0.0

def test_dataset_summary_and_audit_generation(tmp_path):
    matrix_json = tmp_path / "matrix.json"
    matrix_json.write_text(json.dumps([{"test": 1}, {"test": 2}]))
    
    fault_json = tmp_path / "fault.json"
    fault_json.write_text(json.dumps([
        {"experiment_id": "F1", "result": "PASS", "integrity_verified": True},
        {"experiment_id": "F6", "result": "NOT_EXECUTED"}
    ]))

    summary_md = tmp_path / "dataset_summary.md"
    audit_md = tmp_path / "final_data_audit.md"
    plots_dir = tmp_path / "plots"

    generate_dataset_summary(matrix_json, fault_json, summary_md, total_tests=27)
    generate_final_data_audit(matrix_json, fault_json, audit_md, plots_dir)

    assert summary_md.exists()
    assert audit_md.exists()
    assert "Benchmark Datapoints" in summary_md.read_text()
    assert "Final Data Audit Report" in audit_md.read_text()

def test_research_report_generation(tmp_path):
    sum_csv = tmp_path / "summary.csv"
    sum_csv.write_text("file_size_mb,chunk_size_kb,replication_factor,upload_mbps_mean,download_mbps_mean,recovery_sec_mean,mem_mb_mean\n1,512,2,0.73,1.37,0.0,91.8\n")

    fault_csv = tmp_path / "fault_summary.csv"
    fault_csv.write_text("experiment_id,experiment_name,runs,mean_detection_time_seconds,mean_recovery_time_seconds,success_rate,integrity_success_rate\nF1,Node failure,5,0.2,2.78,1.0,1.0\n")

    cov_csv = tmp_path / "fault_coverage.csv"
    cov_csv.write_text("scenario,description,runs,status,success_rate,integrity_success_rate,notes\nF1,Node failure,5,PASS,100%,100%,Executed\n")

    rep_md = tmp_path / "research_report.md"

    generate_report(sum_csv, fault_csv, cov_csv, rep_md)

    assert rep_md.exists()
    content = rep_md.read_text()
    assert "# AirStore: Offline Distributed File Storage" in content
    assert "F1: Node failure" in content
