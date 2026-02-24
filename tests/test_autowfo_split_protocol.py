import importlib
import json

import pytest

from scripts.autowfo import split_protocol as sp


def test_default_split_protocol_contains_expected_fields():
    protocol = sp.load_split_protocol()
    assert protocol["protocol_version"] == "1.0.0"
    assert protocol["default_mode"] == "anchored"
    assert protocol["supported_modes"] == ["anchored", "rolling"]
    assert protocol["constraints"]["allow_oos_overlap"] is False
    # 6-element output schema for 3-way split
    assert len(protocol["output_schema"]["window_tuple"]) == 6
    assert protocol["output_schema"]["window_tuple"] == [
        "train_start", "train_end", "valid_start", "valid_end", "test_start", "test_end"
    ]


def test_validate_split_protocol_rejects_unknown_default_mode(tmp_path):
    protocol = sp.load_split_protocol()
    protocol["default_mode"] = "unsupported_mode"
    path = tmp_path / "invalid_split_protocol.yaml"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    with pytest.raises(ValueError, match="default_mode 'unsupported_mode'"):
        sp.load_split_protocol(str(path))


def test_validate_split_protocol_rejects_missing_segment(tmp_path):
    protocol = sp.load_split_protocol()
    protocol["segments"].pop("test")
    path = tmp_path / "invalid_split_protocol.yaml"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    with pytest.raises(ValueError, match="segments.test"):
        sp.load_split_protocol(str(path))


def test_split_module_fail_fast_when_protocol_invalid(monkeypatch, tmp_path):
    protocol = sp.load_split_protocol()
    protocol["supported_modes"] = [""]
    bad_path = tmp_path / "invalid_split_protocol.yaml"
    bad_path.write_text(json.dumps(protocol), encoding="utf-8")

    import scripts.autowfo.split as split_module
    import scripts.run_btc_regime_sweep as sweep_module

    monkeypatch.setenv(sp.SPLIT_PROTOCOL_PATH_ENV, str(bad_path))
    try:
        with pytest.raises(ValueError, match="supported_modes\\[0\\]"):
            importlib.reload(split_module)
    finally:
        monkeypatch.delenv(sp.SPLIT_PROTOCOL_PATH_ENV, raising=False)
        importlib.reload(split_module)
        importlib.reload(sweep_module)
