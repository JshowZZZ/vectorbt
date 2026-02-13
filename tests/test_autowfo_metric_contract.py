import importlib
import json

import pytest

from scripts.autowfo import metric_contract as mc


def test_default_metric_contract_contains_expected_sections_and_counts():
    contract = mc.load_metric_contract()
    assert contract["contract_version"] == "1.0.0"
    assert len(contract["is_series_metrics"]) == 8
    assert len(contract["combo_metrics"]) == 8
    assert len(contract["is_aggregate_metrics"]) == 8
    assert len(contract["oos_aggregate_metrics"]) == 15


def test_validate_metric_contract_rejects_duplicate_metric_names(tmp_path):
    contract = mc.load_metric_contract()
    contract["is_series_metrics"] = [
        {"name": "dup", "formula": "x"},
        {"name": "dup", "formula": "y"},
    ]
    bad_path = tmp_path / "invalid_metric_contract.yaml"
    bad_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate is_series_metrics metric"):
        mc.load_metric_contract(str(bad_path))


def test_validate_metric_contract_requires_all_sections(tmp_path):
    contract = mc.load_metric_contract()
    contract.pop("oos_aggregate_metrics")
    bad_path = tmp_path / "invalid_metric_contract.yaml"
    bad_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="oos_aggregate_metrics must be a non-empty list"):
        mc.load_metric_contract(str(bad_path))


def test_metrics_module_fail_fast_when_contract_invalid(monkeypatch, tmp_path):
    contract = mc.load_metric_contract()
    contract["combo_metrics"][0]["name"] = ""
    bad_path = tmp_path / "invalid_metric_contract.yaml"
    bad_path.write_text(json.dumps(contract), encoding="utf-8")

    import scripts.autowfo.metrics as metrics_module
    import scripts.run_btc_regime_sweep as sweep_module

    monkeypatch.setenv(mc.METRIC_CONTRACT_PATH_ENV, str(bad_path))
    try:
        with pytest.raises(ValueError, match="combo_metrics\\[0\\]\\.name"):
            importlib.reload(metrics_module)
    finally:
        monkeypatch.delenv(mc.METRIC_CONTRACT_PATH_ENV, raising=False)
        importlib.reload(metrics_module)
        importlib.reload(sweep_module)
