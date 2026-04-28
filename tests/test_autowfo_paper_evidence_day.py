import json
import os
import sqlite3
from pathlib import Path

import pytest


def test_pid_running_handles_current_process_on_windows():
    from autowfo import paper_evidence_day

    assert paper_evidence_day._pid_running(os.getpid()) is True


def _write_live_manifest(path: Path, *, created_utc: str, selection: str = "canonical_gate_passed", rank: int = 1, signals=None):
    payload = {
        "created_utc": created_utc,
        "source_bundle_manifest": str(path.parent.parent / "freqtrade_bridge" / "canonical" / "signal_manifest.json"),
        "analysis": {
            "selection": selection,
            "rank": rank,
            "selected_row": {
                "indicator_list": "obv_roc,keltner_pos",
                "regime_name": "trend_high",
                "timeframe": "2h",
                "data_days": 180,
                "analysis_bucket": selection,
                "analysis_rank": rank,
                "is_canonical_family": selection == "canonical_gate_passed",
            },
        },
        "source": {"pairs": ["LTC/BTC"], "timeframe": "2h"},
        "signals": signals
        or {
            "rows": 6,
            "pairs": ["LTC/BTC"],
            "enter_long_count": 0,
            "enter_short_count": 0,
            "exit_long_count": 0,
            "exit_short_count": 0,
            "last_bar_utc": "2026-04-28T14:00:00",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _summary_payload(*, opened=0, closed=0):
    return {
        "schema_version": "1.0.0",
        "created_utc": "2026-04-29T23:55:00+00:00",
        "date_utc": "2026-04-29",
        "window_start_utc": "2026-04-29T00:00:00+00:00",
        "window_end_utc": "2026-04-30T00:00:00+00:00",
        "analysis": {"selection": "canonical_gate_passed", "rank": 1},
        "source": {"pairs": ["LTC/BTC"], "timeframe": "2h"},
        "pair_mapping": {"LTC/BTC": "LTC/USDT:USDT"},
        "totals": {
            "opened_trades_day": opened,
            "closed_trades_day": closed,
            "entry_signal_match_rate": 1.0 if opened else None,
            "exit_signal_match_rate": 1.0 if closed else None,
        },
        "opened_trades": [{"trade_id": 1, "matched": True}] if opened else [],
        "closed_trades": [{"trade_id": 1, "matched": True}] if closed else [],
    }


def test_collect_phase63_paper_evidence_day_refreshes_stale_manifest_and_classifies_zero_signal(tmp_path, monkeypatch):
    from autowfo import paper_evidence_day

    artifacts = tmp_path / "artifacts"
    live_manifest_path = artifacts / "live_signal_store" / "live_manifest.json"
    manifest_json = artifacts / "freqtrade_bridge" / "canonical" / "signal_manifest.json"
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps({"analysis": {"selection": "canonical_gate_passed", "rank": 1}}), encoding="utf-8")
    _write_live_manifest(
        live_manifest_path,
        created_utc="2026-04-28T00:00:00+00:00",
        selection="top_stable_positive",
        rank=10,
    )

    def fake_load_signal_bundle_manifest(path):
        assert Path(path) == manifest_json.resolve()
        return {"analysis": {"selection": "canonical_gate_passed", "rank": 1}}

    def fake_export_live_signal_store(manifest, *, manifest_path, out_dir, cwd=None, tail_bars=None, staleness_ttl_bars=1.5):
        return _write_live_manifest(
            Path(out_dir) / "live_manifest.json",
            created_utc="2026-04-29T00:10:00+00:00",
            selection="canonical_gate_passed",
            rank=1,
        )

    def fake_reconcile_dryrun_day(**kwargs):
        payload = _summary_payload(opened=0, closed=0)
        out_path = Path(kwargs["out_dir"]) / "daily_summary_20260429.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        payload["out_path"] = str(out_path)
        return payload

    monkeypatch.setattr(paper_evidence_day.freqtrade_bridge, "load_signal_bundle_manifest", fake_load_signal_bundle_manifest)
    monkeypatch.setattr(paper_evidence_day.live_signal_producer, "export_live_signal_store", fake_export_live_signal_store)
    monkeypatch.setattr(paper_evidence_day.paper_dryrun_reconcile, "reconcile_dryrun_day", fake_reconcile_dryrun_day)
    monkeypatch.setattr(
        paper_evidence_day.evidence_warehouse,
        "import_phase63_paper_reconcile_evidence",
        lambda *args, **kwargs: {"ok": True, "warnings": [{"code": "zero_trade_day"}]},
    )
    monkeypatch.setattr(
        paper_evidence_day.evidence_warehouse,
        "build_phase63_paper_survival_report",
        lambda *args, **kwargs: {"ok": True, "verdict_allowed": False, "blocking_reasons": ["zero_trade_day"]},
    )

    payload = paper_evidence_day.collect_phase63_paper_evidence_day(
        artifacts_dir=artifacts,
        manifest_json=manifest_json,
        live_manifest_path=live_manifest_path,
        date_utc="2026-04-29",
        now_utc="2026-04-29T00:20:00+00:00",
        cwd=tmp_path,
    )

    assert payload["ok"] is True
    assert payload["manifest"]["refreshed"] is True
    assert payload["manifest"]["status"] == "fresh"
    assert payload["day_quality"]["classification"] == "zero_trade_day"
    assert payload["zero_trade_reason"] == "strategy_no_signal_today"
    assert payload["zero_signal_explainability"]["signal_window_state"] == "no_entry_or_exit_signals"
    assert Path(payload["health_output_path"]).exists()


def test_collect_phase63_paper_evidence_day_keeps_fresh_manifest_and_marks_trade_day_valid(tmp_path, monkeypatch):
    from autowfo import paper_evidence_day

    artifacts = tmp_path / "artifacts"
    live_manifest_path = artifacts / "live_signal_store" / "live_manifest.json"
    manifest_json = artifacts / "freqtrade_bridge" / "canonical" / "signal_manifest.json"
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps({"analysis": {"selection": "canonical_gate_passed", "rank": 1}}), encoding="utf-8")
    _write_live_manifest(live_manifest_path, created_utc="2026-04-29T00:10:00+00:00")

    def fail_export(*args, **kwargs):
        raise AssertionError("fresh canonical manifest should not be refreshed")

    def fake_reconcile_dryrun_day(**kwargs):
        payload = _summary_payload(opened=1, closed=1)
        out_path = Path(kwargs["out_dir"]) / "daily_summary_20260429.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        payload["out_path"] = str(out_path)
        return payload

    monkeypatch.setattr(paper_evidence_day.live_signal_producer, "export_live_signal_store", fail_export)
    monkeypatch.setattr(paper_evidence_day.paper_dryrun_reconcile, "reconcile_dryrun_day", fake_reconcile_dryrun_day)
    monkeypatch.setattr(
        paper_evidence_day.evidence_warehouse,
        "import_phase63_paper_reconcile_evidence",
        lambda *args, **kwargs: {"ok": True, "warnings": []},
    )
    monkeypatch.setattr(
        paper_evidence_day.evidence_warehouse,
        "build_phase63_paper_survival_report",
        lambda *args, **kwargs: {"ok": True, "verdict_allowed": False, "blocking_reasons": ["insufficient_evidence_days"]},
    )

    payload = paper_evidence_day.collect_phase63_paper_evidence_day(
        artifacts_dir=artifacts,
        manifest_json=manifest_json,
        live_manifest_path=live_manifest_path,
        date_utc="2026-04-29",
        now_utc="2026-04-29T00:20:00+00:00",
        cwd=tmp_path,
    )

    assert payload["manifest"]["refreshed"] is False
    assert payload["day_quality"]["classification"] == "valid_trade_evidence"
    assert payload["day_quality"]["valid_evidence_day"] is True
    assert payload["zero_trade_reason"] is None


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (FileNotFoundError("Freqtrade dry-run DB not found: missing.sqlite"), "missing_freqtrade_db"),
        (sqlite3.DatabaseError("no such table: trades"), "db_trade_table_missing"),
    ],
)
def test_collect_phase63_paper_evidence_day_reports_db_blockers(tmp_path, monkeypatch, exc, expected_code):
    from autowfo import paper_evidence_day

    artifacts = tmp_path / "artifacts"
    live_manifest_path = artifacts / "live_signal_store" / "live_manifest.json"
    manifest_json = artifacts / "freqtrade_bridge" / "canonical" / "signal_manifest.json"
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps({"analysis": {"selection": "canonical_gate_passed", "rank": 1}}), encoding="utf-8")
    _write_live_manifest(live_manifest_path, created_utc="2026-04-29T00:10:00+00:00")

    def fake_reconcile_dryrun_day(**kwargs):
        raise exc

    monkeypatch.setattr(paper_evidence_day.paper_dryrun_reconcile, "reconcile_dryrun_day", fake_reconcile_dryrun_day)

    payload = paper_evidence_day.collect_phase63_paper_evidence_day(
        artifacts_dir=artifacts,
        manifest_json=manifest_json,
        live_manifest_path=live_manifest_path,
        date_utc="2026-04-29",
        now_utc="2026-04-29T00:20:00+00:00",
        cwd=tmp_path,
    )

    assert payload["ok"] is False
    assert payload["failure_code"] == expected_code
    assert expected_code in payload["health_blocking_reasons"]
    assert payload["day_quality"]["classification"] == "invalid_runtime"
    assert Path(payload["health_output_path"]).exists()
