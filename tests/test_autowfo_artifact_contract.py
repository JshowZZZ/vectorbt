import importlib
import json

import pytest

from autowfo import artifact_contract as ac


def test_default_artifact_contract_contains_expected_sections():
    contract = ac.load_artifact_contract()
    assert contract["contract_version"] == "1.0.0"
    assert "run_metadata.json" in contract["required_files"]
    assert contract["row_metadata_fields"] == ["config_sha256", "data_fingerprint"]
    assert "config_sha256" in contract["run_metadata_fields"]
    assert "combo_seed" in contract["run_metadata_fields"]


def test_validate_artifact_contract_rejects_duplicate_required_files(tmp_path):
    contract = ac.load_artifact_contract()
    contract["required_files"] = ["a.json", "a.json"]
    path = tmp_path / "invalid_artifact_contract.yaml"
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate required_files"):
        ac.load_artifact_contract(str(path))


def test_validate_artifact_contract_requires_run_metadata_fields(tmp_path):
    contract = ac.load_artifact_contract()
    contract["run_metadata_fields"] = []
    path = tmp_path / "invalid_artifact_contract.yaml"
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="run_metadata_fields must be a non-empty list"):
        ac.load_artifact_contract(str(path))


def test_artifacts_module_fail_fast_when_contract_invalid(monkeypatch, tmp_path):
    contract = ac.load_artifact_contract()
    contract["row_metadata_fields"][0] = ""
    bad_path = tmp_path / "invalid_artifact_contract.yaml"
    bad_path.write_text(json.dumps(contract), encoding="utf-8")

    import autowfo.artifacts as artifacts_module
    import autowfo.run_btc_regime_sweep as sweep_module

    monkeypatch.setenv(ac.ARTIFACT_CONTRACT_PATH_ENV, str(bad_path))
    try:
        with pytest.raises(ValueError, match="row_metadata_fields\\[0\\]"):
            importlib.reload(artifacts_module)
    finally:
        monkeypatch.delenv(ac.ARTIFACT_CONTRACT_PATH_ENV, raising=False)
        importlib.reload(artifacts_module)
        importlib.reload(sweep_module)

