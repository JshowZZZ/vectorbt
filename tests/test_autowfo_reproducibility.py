import json

import pandas as pd

from autowfo import artifact_contract as ac
from autowfo import reproducibility as rep


def test_compare_top_n_stability_identical_rows_are_stable():
    reference = pd.DataFrame(
        [
            {"combo_id": "A", "score": 10.0, "oos_avg_total_return_pct": 5.0},
            {"combo_id": "B", "score": 9.0, "oos_avg_total_return_pct": 4.0},
        ]
    )
    candidate = pd.DataFrame(
        [
            {"combo_id": "A", "score": 10.0, "oos_avg_total_return_pct": 5.0},
            {"combo_id": "B", "score": 9.0, "oos_avg_total_return_pct": 4.0},
        ]
    )

    got = rep.compare_top_n_stability(
        reference,
        candidate,
        top_n=2,
        identity_fields=("combo_id",),
        metric_fields=("oos_avg_total_return_pct",),
        metric_abs_tolerance=1e-9,
    )

    assert got["stable"] is True
    assert got["identity_match"] is True
    assert got["metric_match"] is True
    assert got["overlap_rows"] == 2
    assert got["reference_only_rows"] == 0
    assert got["candidate_only_rows"] == 0
    assert got["metric_deltas"]["oos_avg_total_return_pct"]["max_abs_delta"] == 0.0


def test_compare_top_n_stability_detects_identity_drift():
    reference = pd.DataFrame(
        [
            {"combo_id": "A", "score": 10.0, "oos_avg_total_return_pct": 5.0},
            {"combo_id": "B", "score": 9.0, "oos_avg_total_return_pct": 4.0},
        ]
    )
    candidate = pd.DataFrame(
        [
            {"combo_id": "A", "score": 10.0, "oos_avg_total_return_pct": 5.0},
            {"combo_id": "C", "score": 8.5, "oos_avg_total_return_pct": 3.5},
        ]
    )

    got = rep.compare_top_n_stability(
        reference,
        candidate,
        top_n=2,
        identity_fields=("combo_id",),
        metric_fields=("oos_avg_total_return_pct",),
    )

    assert got["stable"] is False
    assert got["identity_match"] is False
    assert got["overlap_rows"] == 1
    assert got["reference_only_rows"] == 1
    assert got["candidate_only_rows"] == 1
    assert got["reference_only"] == [{"combo_id": "B"}]
    assert got["candidate_only"] == [{"combo_id": "C"}]


def test_compare_top_n_stability_respects_metric_tolerance():
    reference = pd.DataFrame(
        [
            {"combo_id": "A", "oos_avg_total_return_pct": 5.0},
            {"combo_id": "B", "oos_avg_total_return_pct": 4.0},
        ]
    )
    candidate = pd.DataFrame(
        [
            {"combo_id": "A", "oos_avg_total_return_pct": 5.0002},
            {"combo_id": "B", "oos_avg_total_return_pct": 3.9999},
        ]
    )

    loose = rep.compare_top_n_stability(
        reference,
        candidate,
        top_n=2,
        identity_fields=("combo_id",),
        metric_fields=("oos_avg_total_return_pct",),
        metric_abs_tolerance=5e-4,
    )
    tight = rep.compare_top_n_stability(
        reference,
        candidate,
        top_n=2,
        identity_fields=("combo_id",),
        metric_fields=("oos_avg_total_return_pct",),
        metric_abs_tolerance=1e-5,
    )

    assert loose["identity_match"] is True
    assert loose["metric_match"] is True
    assert loose["stable"] is True

    assert tight["identity_match"] is True
    assert tight["metric_match"] is False
    assert tight["stable"] is False
    assert tight["metric_deltas"]["oos_avg_total_return_pct"]["max_abs_delta"] > 1e-4


def test_validate_run_artifact_schema_passes_when_required_files_and_fields_exist(tmp_path):
    contract = ac.load_artifact_contract()
    run_dir = tmp_path / "run_combo"
    run_dir.mkdir(parents=True, exist_ok=True)

    required_files = contract["required_files"]
    for filename in required_files:
        path = run_dir / filename
        if filename.endswith(".csv"):
            path.write_text("config_sha256,data_fingerprint\nabc,def\n", encoding="utf-8")
        elif filename == "run_metadata.json":
            payload = {field: "ok" for field in contract["run_metadata_fields"]}
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_text("ok", encoding="utf-8")

    got = rep.validate_run_artifact_schema(run_dir, contract_payload=contract)
    assert got["valid"] is True
    assert got["missing_required_files"] == []
    assert got["run_metadata_missing_fields"] == []
    assert got["row_metadata_missing_by_file"] == {}


def test_validate_run_artifact_schema_detects_missing_metadata_fields(tmp_path):
    contract = ac.load_artifact_contract()
    run_dir = tmp_path / "run_combo"
    run_dir.mkdir(parents=True, exist_ok=True)

    for filename in contract["required_files"]:
        path = run_dir / filename
        if filename.endswith(".csv"):
            path.write_text("config_sha256\nabc\n", encoding="utf-8")
        elif filename == "run_metadata.json":
            payload = {field: "ok" for field in contract["run_metadata_fields"] if field != "combo_seed"}
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_text("ok", encoding="utf-8")

    got = rep.validate_run_artifact_schema(run_dir, contract_payload=contract)
    assert got["valid"] is False
    assert got["run_metadata_missing_fields"] == ["combo_seed"]
    assert "param_sweep_combo_summary.csv" in got["row_metadata_missing_by_file"]

