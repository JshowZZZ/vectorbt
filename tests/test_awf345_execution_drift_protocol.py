import json
from pathlib import Path


def test_execution_drift_report_v1_protocol_has_required_sections():
    payload = json.loads(
        Path("plans/protocols/execution_drift_report_v1.json").read_text(encoding="utf-8")
    )

    assert payload["awf_id"] == "AWF-345"
    assert payload["name"] == "execution_drift_report_v1"
    assert payload["schema_version"] == "1.0.0"

    sections = payload["report_sections"]
    assert set(sections.keys()) == {
        "row_level_drift",
        "pair_direction_drift",
        "source_consistency",
    }

    row_fields = sections["row_level_drift"]["required_fields"]
    assert "row_id" in row_fields
    assert "open_match_ratio" in row_fields
    assert "exact_match_ratio" in row_fields
    assert "drift_severity" in row_fields

    pair_fields = sections["pair_direction_drift"]["required_fields"]
    assert pair_fields[:3] == ["row_id", "pair", "direction"]
    assert "delta" in pair_fields

    source_fields = sections["source_consistency"]["required_fields"]
    assert "signal_bundle_id" in source_fields
    assert "parity_bundle_id" in source_fields
    assert "signal_manifest_joined" in source_fields
    assert "parity_report_joined" in source_fields

    invariants = payload["artifact_contract"]["invariants"]
    assert any("signal_manifest_joined" in item for item in invariants)
    assert any("parity_report_joined" in item for item in invariants)
