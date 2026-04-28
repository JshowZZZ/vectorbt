"""One-day Phase 63 paper evidence collection helpers."""

from __future__ import annotations

import json
import os
import sqlite3
import ctypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from autowfo import evidence_warehouse
from autowfo import freqtrade_bridge
from autowfo import live_signal_producer
from autowfo import paper_dryrun_reconcile


PAPER_EVIDENCE_DAY_SCHEMA_VERSION = "phase63_paper_evidence_day/v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_path(cwd: Path, value: str | Path | None, default: str | Path) -> Path:
    raw = Path(str(value if value not in (None, "") else default))
    if raw.is_absolute():
        return raw.resolve()
    return (cwd / raw).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _default_day(now_utc: datetime) -> str:
    return now_utc.strftime("%Y-%m-%d")


def _day_label(date_utc: str) -> str:
    return str(date_utc).replace("-", "")


def _manifest_status(
    live_manifest: Mapping[str, Any] | None,
    *,
    expected_selection: str,
    expected_rank: int,
    freshness_minutes: int,
    now_utc: datetime,
) -> dict[str, Any]:
    if not live_manifest:
        return {"status": "missing", "age_minutes": None, "selection": "", "rank": None}
    analysis = live_manifest.get("analysis")
    analysis_obj = analysis if isinstance(analysis, Mapping) else {}
    selection = str(analysis_obj.get("selection") or "")
    rank = analysis_obj.get("rank")
    created = _parse_utc(live_manifest.get("created_utc"))
    age_minutes = ((now_utc - created).total_seconds() / 60.0) if created else None
    if selection != expected_selection or str(rank) != str(expected_rank):
        status = "wrong_lane"
    elif age_minutes is None:
        status = "missing_freshness"
    elif age_minutes > int(freshness_minutes):
        status = "stale"
    else:
        status = "fresh"
    return {
        "status": status,
        "age_minutes": age_minutes,
        "selection": selection,
        "rank": rank,
        "created_utc": live_manifest.get("created_utc"),
    }


def _pid_running(pid: Any) -> bool | None:
    try:
        pid_int = int(pid)
    except Exception:
        return None
    if pid_int <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        process_query_limited_information = 0x1000
        still_active = 259
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid_int)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if not ok:
                return None
            return int(exit_code.value) == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid_int, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _managed_status(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"state_path": str(state_path), "pid": None, "running": None, "started_utc": None}
    try:
        payload = _read_json(state_path)
    except Exception as exc:
        return {
            "state_path": str(state_path),
            "pid": None,
            "running": None,
            "started_utc": None,
            "error": str(exc),
        }
    return {
        "state_path": str(state_path),
        "pid": payload.get("pid"),
        "running": _pid_running(payload.get("pid")),
        "started_utc": payload.get("started_utc"),
        "stdout_log": payload.get("stdout_log"),
        "stderr_log": payload.get("stderr_log"),
    }


def _runtime_status(paper_dir: Path) -> dict[str, Any]:
    runtime_dir = paper_dir / "runtime"
    return {
        "live_signal_producer": _managed_status(runtime_dir / "live_signal_producer.json"),
        "freqtrade_dryrun": _managed_status(runtime_dir / "freqtrade_dryrun.json"),
    }


def _manifest_blocking_reason(status: str) -> str | None:
    if status == "wrong_lane":
        return "manifest_wrong_lane"
    if status in {"stale", "missing_freshness"}:
        return "manifest_stale"
    if status == "missing":
        return "missing_live_manifest"
    if status == "unreadable":
        return "unreadable_live_manifest"
    return None


def _summary_counts(summary: Mapping[str, Any]) -> tuple[int, int]:
    totals = summary.get("totals")
    opened = len(summary.get("opened_trades") or [])
    closed = len(summary.get("closed_trades") or [])
    if isinstance(totals, Mapping):
        opened = int(totals.get("opened_trades_day") or opened or 0)
        closed = int(totals.get("closed_trades_day") or closed or 0)
    return opened, closed


def _has_missing_match_rate(summary: Mapping[str, Any], opened: int, closed: int) -> bool:
    totals = summary.get("totals")
    if not isinstance(totals, Mapping):
        return opened > 0 or closed > 0
    return (opened > 0 and totals.get("entry_signal_match_rate") is None) or (
        closed > 0 and totals.get("exit_signal_match_rate") is None
    )


def _signals(live_manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = live_manifest.get("signals")
    return raw if isinstance(raw, Mapping) else {}


def _signal_activity(live_manifest: Mapping[str, Any]) -> dict[str, int]:
    signals = _signals(live_manifest)
    return {
        "rows": int(signals.get("rows") or 0),
        "enter_long_count": int(signals.get("enter_long_count") or 0),
        "enter_short_count": int(signals.get("enter_short_count") or 0),
        "exit_long_count": int(signals.get("exit_long_count") or 0),
        "exit_short_count": int(signals.get("exit_short_count") or 0),
    }


def _zero_signal_explainability(live_manifest: Mapping[str, Any]) -> dict[str, Any]:
    activity = _signal_activity(live_manifest)
    signal_total = (
        activity["enter_long_count"]
        + activity["enter_short_count"]
        + activity["exit_long_count"]
        + activity["exit_short_count"]
    )
    selected_row = (live_manifest.get("analysis") or {}).get("selected_row") if isinstance(live_manifest.get("analysis"), Mapping) else {}
    selected = selected_row if isinstance(selected_row, Mapping) else {}
    if activity["rows"] <= 0:
        state = "empty_signal_window"
    elif signal_total <= 0:
        state = "no_entry_or_exit_signals"
    else:
        state = "entry_or_exit_signals_present"
    return {
        "signal_window_state": state,
        **activity,
        "indicator_list": selected.get("indicator_list") or selected.get("canonical_indicator_list"),
        "regime_name": selected.get("regime_name"),
        "timeframe": selected.get("timeframe") or (live_manifest.get("source") or {}).get("timeframe"),
        "last_bar_utc": _signals(live_manifest).get("last_bar_utc"),
    }


def _pair_mapping_gap(summary: Mapping[str, Any]) -> bool:
    source = summary.get("source")
    source_obj = source if isinstance(source, Mapping) else {}
    source_pairs = {str(item) for item in (source_obj.get("pairs") or []) if str(item).strip()}
    mapping = summary.get("pair_mapping")
    mapping_obj = mapping if isinstance(mapping, Mapping) else {}
    mapped_pairs = {str(item) for item in mapping_obj.keys() if str(item).strip()}
    return bool(source_pairs and not source_pairs.issubset(mapped_pairs))


def _classify_zero_trade_reason(
    *,
    manifest_status: str,
    live_manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> str | None:
    opened, closed = _summary_counts(summary)
    if opened or closed:
        return None
    manifest_reason = _manifest_blocking_reason(manifest_status)
    if manifest_reason in {"manifest_wrong_lane", "manifest_stale"}:
        return manifest_reason
    activity = _signal_activity(live_manifest)
    if activity["rows"] <= 0:
        return "signal_rows_empty"
    if _pair_mapping_gap(summary):
        return "pair_mapping_gap"
    freqtrade_status = runtime.get("freqtrade_dryrun") if isinstance(runtime, Mapping) else {}
    if isinstance(freqtrade_status, Mapping) and freqtrade_status.get("running") is False:
        return "freqtrade_process_down"
    if (
        activity["enter_long_count"]
        + activity["enter_short_count"]
        + activity["exit_long_count"]
        + activity["exit_short_count"]
    ) == 0:
        return "strategy_no_signal_today"
    return "unknown"


def _day_quality(
    *,
    manifest_status: str,
    summary: Mapping[str, Any] | None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    if failure_code in {"missing_freqtrade_db", "db_trade_table_missing"}:
        return {"classification": "invalid_runtime", "valid_evidence_day": False}
    if manifest_status != "fresh":
        return {"classification": "invalid_manifest", "valid_evidence_day": False}
    if summary is None:
        return {"classification": "invalid_runtime", "valid_evidence_day": False}
    opened, closed = _summary_counts(summary)
    if _has_missing_match_rate(summary, opened, closed):
        return {"classification": "invalid_match_rate", "valid_evidence_day": False}
    if opened == 0 and closed == 0:
        return {"classification": "zero_trade_day", "valid_evidence_day": False}
    return {"classification": "valid_trade_evidence", "valid_evidence_day": True}


def _failure_code(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, FileNotFoundError) and "db" in message:
        return "missing_freqtrade_db"
    if isinstance(exc, sqlite3.DatabaseError) and "no such table" in message and "trades" in message:
        return "db_trade_table_missing"
    return "reconcile_failed"


def collect_phase63_paper_evidence_day(
    *,
    manifest_json: str | Path,
    artifacts_dir: str | Path = "artifacts",
    live_manifest_path: str | Path = "artifacts/live_signal_store/live_manifest.json",
    live_signal_out_dir: str | Path = "artifacts/live_signal_store",
    paper_dir: str | Path = "artifacts/paper_dryrun",
    freqtrade_config_path: str | Path | None = None,
    freqtrade_db_path: str | Path | None = None,
    warehouse_db_path: str | Path | None = None,
    protocol_path: str | Path | None = None,
    date_utc: str | None = None,
    min_date_utc: str | None = None,
    cwd: str | Path = ".",
    freshness_minutes: int = 30,
    expected_selection: str = "canonical_gate_passed",
    expected_rank: int = 1,
    refresh_if_needed: bool = True,
    tail_bars: int | None = None,
    staleness_ttl_bars: float = 1.5,
    now_utc: str | datetime | None = None,
) -> dict[str, Any]:
    """Collect one Phase 63 paper evidence day and write a health artifact."""

    cwd_path = Path(cwd).resolve()
    artifacts_path = _resolve_path(cwd_path, artifacts_dir, "artifacts")
    paper_path = _resolve_path(cwd_path, paper_dir, "artifacts/paper_dryrun")
    live_manifest = _resolve_path(cwd_path, live_manifest_path, "artifacts/live_signal_store/live_manifest.json")
    live_out = _resolve_path(cwd_path, live_signal_out_dir, "artifacts/live_signal_store")
    manifest_path = _resolve_path(cwd_path, manifest_json, manifest_json)
    now = _parse_utc(now_utc) if now_utc is not None else _utc_now()
    if now is None:
        now = _utc_now()
    resolved_date = str(date_utc or "").strip() or _default_day(now)
    health_path = paper_path / "health" / f"phase63_paper_health_{_day_label(resolved_date)}.json"

    runtime = _runtime_status(paper_path)
    live_payload: dict[str, Any] = {}
    initial_status = {"status": "missing", "age_minutes": None, "selection": "", "rank": None}
    if live_manifest.exists():
        try:
            live_payload = _read_json(live_manifest)
            initial_status = _manifest_status(
                live_payload,
                expected_selection=expected_selection,
                expected_rank=expected_rank,
                freshness_minutes=freshness_minutes,
                now_utc=now,
            )
        except Exception:
            initial_status = {"status": "unreadable", "age_minutes": None, "selection": "", "rank": None}

    refreshed = False
    if initial_status["status"] != "fresh" and refresh_if_needed:
        bundle_manifest = freqtrade_bridge.load_signal_bundle_manifest(manifest_path)
        live_payload = live_signal_producer.export_live_signal_store(
            bundle_manifest,
            manifest_path=manifest_path,
            out_dir=live_out,
            cwd=cwd_path,
            tail_bars=tail_bars,
            staleness_ttl_bars=staleness_ttl_bars,
        )
        refreshed = True

    final_status = _manifest_status(
        live_payload,
        expected_selection=expected_selection,
        expected_rank=expected_rank,
        freshness_minutes=freshness_minutes,
        now_utc=now,
    )

    manifest_blocker = _manifest_blocking_reason(str(final_status["status"]))
    if final_status["status"] != "fresh":
        payload = {
            "ok": False,
            "schema_version": PAPER_EVIDENCE_DAY_SCHEMA_VERSION,
            "date_utc": resolved_date,
            "failure_code": manifest_blocker or "invalid_manifest",
            "health_blocking_reasons": [manifest_blocker or "invalid_manifest"],
            "manifest": {**final_status, "initial_status": initial_status["status"], "refreshed": refreshed},
            "runtime": runtime,
            "day_quality": _day_quality(manifest_status=str(final_status["status"]), summary=None),
            "zero_trade_reason": manifest_blocker,
            "health_output_path": str(health_path),
        }
        _write_json(health_path, payload)
        return payload

    try:
        summary = paper_dryrun_reconcile.reconcile_dryrun_day(
            live_manifest_path=live_manifest,
            out_dir=paper_path,
            freqtrade_config_path=freqtrade_config_path,
            db_path=freqtrade_db_path,
            day_utc=resolved_date,
            cwd=cwd_path,
        )
    except Exception as exc:
        code = _failure_code(exc)
        payload = {
            "ok": False,
            "schema_version": PAPER_EVIDENCE_DAY_SCHEMA_VERSION,
            "date_utc": resolved_date,
            "failure_code": code,
            "failure_message": str(exc),
            "health_blocking_reasons": [code],
            "manifest": {**final_status, "initial_status": initial_status["status"], "refreshed": refreshed},
            "runtime": runtime,
            "day_quality": _day_quality(manifest_status=str(final_status["status"]), summary=None, failure_code=code),
            "zero_trade_reason": "db_trade_table_missing" if code == "db_trade_table_missing" else None,
            "health_output_path": str(health_path),
        }
        _write_json(health_path, payload)
        return payload

    warehouse_payload = evidence_warehouse.import_phase63_paper_reconcile_evidence(
        artifacts_path,
        protocol_path=protocol_path,
        db_path=warehouse_db_path,
        paper_dir=paper_path,
        live_manifest_path=live_manifest,
    )
    survival_report = evidence_warehouse.build_phase63_paper_survival_report(
        artifacts_path,
        paper_dir=paper_path,
        expected_selection=expected_selection,
        expected_rank=expected_rank,
        min_date_utc=min_date_utc,
    )
    quality = _day_quality(manifest_status=str(final_status["status"]), summary=summary)
    zero_trade_reason = _classify_zero_trade_reason(
        manifest_status=str(final_status["status"]),
        live_manifest=live_payload,
        summary=summary,
        runtime=runtime,
    )
    opened, closed = _summary_counts(summary)
    payload = {
        "ok": True,
        "schema_version": PAPER_EVIDENCE_DAY_SCHEMA_VERSION,
        "date_utc": resolved_date,
        "manifest": {**final_status, "initial_status": initial_status["status"], "refreshed": refreshed},
        "runtime": runtime,
        "reconcile": {
            "out_path": summary.get("out_path"),
            "opened_trades_day": opened,
            "closed_trades_day": closed,
            "entry_signal_match_rate": (summary.get("totals") or {}).get("entry_signal_match_rate")
            if isinstance(summary.get("totals"), Mapping)
            else None,
            "exit_signal_match_rate": (summary.get("totals") or {}).get("exit_signal_match_rate")
            if isinstance(summary.get("totals"), Mapping)
            else None,
        },
        "warehouse_import": warehouse_payload,
        "warehouse_warnings": warehouse_payload.get("warnings") or [],
        "survival_report": survival_report,
        "day_quality": quality,
        "zero_trade_reason": zero_trade_reason,
        "zero_signal_explainability": _zero_signal_explainability(live_payload),
        "health_blocking_reasons": list(survival_report.get("blocking_reasons") or []),
        "health_output_path": str(health_path),
    }
    _write_json(health_path, payload)
    return payload
