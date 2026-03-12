"""Patrol/cron analytics helpers for AUTOWFO commands."""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from .core_batch import (
    _load_batch_state,
    _parse_batch_jobs,
    _run_batch_job_single,
    _run_batch_jobs_parallel,
)
from .core_utils import (
    _build_timeframe_days_map,
    _compute_coverage_gaps,
    _extract_registry_untested_pairs,
    _load_config,
    _slug_text,
    _utc_now_iso,
)


def _cmd_plan(_args: argparse.Namespace) -> int:
    raise RuntimeError("_cmd_plan is not bound")


def _cmd_batch(_args: argparse.Namespace) -> int:
    raise RuntimeError("_cmd_batch is not bound")


def _cmd_report(_args: argparse.Namespace) -> int:
    raise RuntimeError("_cmd_report is not bound")


PATROL_LOG_MAX_LINES_DEFAULT = 1000
PATROL_LOG_KEEP_LINES_DEFAULT = 500

def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _parse_datetime_utc(raw_value: Any) -> Optional[datetime]:
    text = str(raw_value or "").strip()
    if not text:
        return None

    candidates = [text]
    if " " in text and "T" not in text:
        candidates.insert(0, text.replace(" ", "T"))

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            dt = None
        if dt is not None:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

def _trim_text(text: str, max_len: int = 96) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_len:
        return raw
    return f"{raw[: max_len - 3]}..."

def _extract_top_entities(report_payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(report_payload, dict):
        return out

    combo_rows = report_payload.get("combo_stability")
    if isinstance(combo_rows, list):
        for row in combo_rows:
            if not isinstance(row, dict):
                continue
            combo_key = str(row.get("combo_key", "")).strip()
            if not combo_key:
                continue
            out.append(
                {
                    "key": combo_key,
                    "label": combo_key,
                    "kind": "combo",
                    "value": _safe_float(row.get("avg_oos_return_pct")),
                }
            )
            if len(out) >= limit:
                return out

    leaderboard_rows = report_payload.get("global_leaderboard")
    if isinstance(leaderboard_rows, list):
        for row in leaderboard_rows:
            if not isinstance(row, dict):
                continue
            run_id = str(row.get("run_id", "")).strip()
            if not run_id:
                continue
            out.append(
                {
                    "key": run_id,
                    "label": run_id,
                    "kind": "run",
                    "value": _safe_float(row.get("oos_avg_total_return_pct")),
                }
            )
            if len(out) >= limit:
                return out
    return out

def _build_top_change_lines(
    previous_top: List[Dict[str, Any]],
    current_top: List[Dict[str, Any]],
    *,
    limit: int,
) -> List[str]:
    if limit <= 0:
        return []

    prev_rank: Dict[str, int] = {}
    for idx, item in enumerate(previous_top[:limit], start=1):
        key = str(item.get("key", "")).strip()
        if key:
            prev_rank[key] = idx

    lines: List[str] = []
    for idx, item in enumerate(current_top[:limit], start=1):
        key = str(item.get("key", "")).strip()
        label = _trim_text(str(item.get("label", "")).strip())
        value = _safe_float(item.get("value"))

        old_rank = prev_rank.get(key)
        if old_rank is None:
            tag = "NEW"
        elif old_rank == idx:
            tag = "SAME"
        elif old_rank > idx:
            tag = f"UP {old_rank}->{idx}"
        else:
            tag = f"DOWN {old_rank}->{idx}"

        metric = "n/a" if value is None else f"{value:.4f}%"
        lines.append(f"{idx}. [{tag}] {label} ({metric})")

    if not lines:
        lines.append("n/a")
    return lines

def _default_cron_notify_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_utc": _utc_now_iso(),
        "last_top": [],
    }

def _read_cron_notify_state(path: Path) -> Dict[str, Any]:
    state = _default_cron_notify_state()
    if not path.exists():
        return state

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return state
    if not isinstance(payload, dict):
        return state

    raw_last_top = payload.get("last_top")
    last_top: List[Dict[str, Any]] = []
    if isinstance(raw_last_top, list):
        for item in raw_last_top:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if not key:
                continue
            last_top.append(
                {
                    "key": key,
                    "label": str(item.get("label", key)),
                    "kind": str(item.get("kind", "")).strip() or "combo",
                    "value": _safe_float(item.get("value")),
                }
            )

    state["version"] = int(payload.get("version", 1) or 1)
    state["updated_utc"] = str(payload.get("updated_utc", _utc_now_iso()))
    state["last_top"] = last_top
    return state

def _write_cron_notify_state(path: Path, payload: Dict[str, Any]) -> None:
    state = _default_cron_notify_state()
    state.update(payload if isinstance(payload, dict) else {})
    state["updated_utc"] = _utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def _build_freshness_alert(artifacts_dir: Path, threshold_days: int) -> Dict[str, Any]:
    threshold_days = max(1, int(threshold_days))
    state_path = artifacts_dir / "data_refresh_state.json"
    now_utc = datetime.now(timezone.utc)
    output: Dict[str, Any] = {
        "checked": False,
        "alert": False,
        "threshold_days": threshold_days,
        "stale": [],
    }
    if not state_path.exists():
        return output

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return output
    if not isinstance(payload, dict):
        return output

    timeframe_data_end = payload.get("timeframe_data_end")
    if not isinstance(timeframe_data_end, dict):
        return output

    stale_rows: List[Dict[str, Any]] = []
    for timeframe, raw_mark in timeframe_data_end.items():
        dt = _parse_datetime_utc(raw_mark)
        if dt is None:
            continue
        age_seconds = max(0.0, (now_utc - dt).total_seconds())
        age_days = int(age_seconds // 86400)
        if age_days > threshold_days:
            stale_rows.append(
                {
                    "timeframe": str(timeframe),
                    "data_end": str(raw_mark),
                    "days_stale": age_days,
                }
            )

    stale_rows.sort(key=lambda item: int(item.get("days_stale", 0)), reverse=True)
    output["checked"] = True
    output["stale"] = stale_rows
    output["alert"] = bool(stale_rows)
    return output

def _format_freshness_line(freshness_alert: Dict[str, Any]) -> str:
    if not freshness_alert.get("checked"):
        return "freshness=unknown (data_refresh_state missing)"
    if not freshness_alert.get("alert"):
        return "freshness=ok"

    stale_rows = freshness_alert.get("stale")
    if not isinstance(stale_rows, list):
        stale_rows = []
    preview = []
    for row in stale_rows[:3]:
        timeframe = str(row.get("timeframe", "")).strip()
        days = int(row.get("days_stale", 0) or 0)
        if timeframe:
            preview.append(f"{timeframe}:{days}d")
    threshold_days = int(freshness_alert.get("threshold_days", 7) or 7)
    joined = ", ".join(preview) if preview else "n/a"
    return f"freshness=ALERT(>{threshold_days}d) {joined}"

def _post_json(url: str, payload: Dict[str, Any], timeout_seconds: int = 10) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
        status = int(getattr(resp, "status", 200))
        if status >= 400:
            raise RuntimeError(f"http {status}")

def _dispatch_cron_notifications(
    *,
    webhook_urls: List[str],
    telegram_token: str,
    telegram_chat_id: str,
    message_text: str,
    payload: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []

    for webhook_url in webhook_urls:
        try:
            _post_json(webhook_url, payload)
        except Exception as exc:
            errors.append(f"webhook {webhook_url}: {exc}")

    if telegram_token and telegram_chat_id:
        tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        tg_payload = {
            "chat_id": telegram_chat_id,
            "text": message_text,
            "disable_web_page_preview": True,
        }
        try:
            _post_json(tg_url, tg_payload)
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, ValueError) as exc:
            errors.append(f"telegram: {exc}")
    return errors

def _build_cron_notification_text(
    *,
    cycle_number: int,
    status: str,
    cycle_result: Dict[str, Any],
    top_change_lines: List[str],
    freshness_alert: Dict[str, Any],
) -> str:
    lines = [
        f"[AUTOWFO][cron] cycle {cycle_number} {status}",
        "plan_jobs={plan_jobs} batch_ok={batch_ok} report_ok={report_ok}".format(
            plan_jobs=cycle_result.get("plan_jobs", 0),
            batch_ok=bool(cycle_result.get("batch_ok")),
            report_ok=bool(cycle_result.get("report_ok")),
        ),
        "top:",
    ]
    lines.extend(top_change_lines or ["n/a"])
    lines.append(_format_freshness_line(freshness_alert))
    err = str(cycle_result.get("error") or "").strip()
    if err:
        lines.append(f"error={_trim_text(err, max_len=200)}")
    return "\n".join(lines)


def _rotate_patrol_log(
    log_path: Path,
    *,
    max_lines: int = PATROL_LOG_MAX_LINES_DEFAULT,
    keep_lines: int = PATROL_LOG_KEEP_LINES_DEFAULT,
) -> None:
    max_n = max(1, int(max_lines))
    keep_n = max(1, min(int(keep_lines), max_n))
    if not log_path.exists():
        return

    lines = log_path.read_text(encoding="utf-8-sig").splitlines()
    if len(lines) <= max_n:
        return

    tail = lines[-keep_n:]
    tmp_path = log_path.with_suffix(f"{log_path.suffix}.tmp.{os.getpid()}")
    try:
        payload = "\n".join(tail)
        if payload:
            payload += "\n"
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, log_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _append_patrol_log(
    cwd: Path,
    cycle_result: Dict[str, Any],
    *,
    max_lines: int = PATROL_LOG_MAX_LINES_DEFAULT,
    keep_lines: int = PATROL_LOG_KEEP_LINES_DEFAULT,
) -> None:
    artifacts_dir = Path(cwd) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifacts_dir / "patrol_log.ndjson"

    discovery_tick = cycle_result.get("discovery_tick")
    if not isinstance(discovery_tick, dict):
        discovery_tick = {}

    run_outcomes = cycle_result.get("scheduler_run_outcomes")
    if not isinstance(run_outcomes, list):
        run_outcomes = []

    runs_executed = int(cycle_result.get("scheduler_runs_processed", 0) or 0)
    runs_errors = int(
        sum(1 for row in run_outcomes if isinstance(row, dict) and row.get("processed") and not row.get("ok", True))
    )
    queue_remaining = int(cycle_result.get("queue_remaining", 0) or 0)

    row = {
        "utc": str(cycle_result.get("cycle_end_utc") or _utc_now_iso()),
        "tick_generated": int(discovery_tick.get("generated", 0) or 0),
        "tick_enqueued": int(discovery_tick.get("enqueued", 0) or 0),
        "runs_executed": runs_executed,
        "runs_errors": runs_errors,
        "queue_remaining": queue_remaining,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _rotate_patrol_log(log_path, max_lines=max_lines, keep_lines=keep_lines)

def _run_patrol_cycle(
    cwd: Path,
    registry_path: Path,
    template_config_path: Path,
    plan_out: Path,
    plan_config_dir: Path,
    batch_state_path: Path,
    report_html_path: Path,
    report_json_path: Optional[Path],
    *,
    workflow: str = "run",
    mode: Optional[str] = "combo",
    workers: Optional[int] = None,
    max_jobs: int = 0,
    continue_on_error: bool = True,
    parallel_jobs: int = 1,
    top_n: int = 20,
    target_timeframes: Optional[List[str]] = None,
    target_symbols: Optional[List[str]] = None,
    timeframe_days_map: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Execute one plan → batch → report cycle.

    Returns a summary dict with ``plan_jobs``, ``batch_ok``, ``report_ok``,
    ``error`` (None on success).
    """
    result: Dict[str, Any] = {
        "cycle_start_utc": _utc_now_iso(),
        "plan_jobs": 0,
        "batch_ok": False,
        "report_ok": False,
        "error": None,
        "top_entities": [],
    }

    # --- 1. Plan -----------------------------------------------------------
    try:
        registry_payload = _load_config(registry_path)
        template_config = _load_config(template_config_path)

        if target_timeframes and target_symbols:
            pairs = _compute_coverage_gaps(registry_payload, list(target_timeframes), list(target_symbols))
        else:
            pairs = _extract_registry_untested_pairs(registry_payload)

        if max_jobs and max_jobs > 0:
            pairs = pairs[:max_jobs]

        td_map = _build_timeframe_days_map(registry_payload, template_config)
        if timeframe_days_map:
            td_map.update(timeframe_days_map)

        default_days = 60
        template_timeframes_raw = template_config.get("timeframes")
        if isinstance(template_timeframes_raw, list):
            for item in template_timeframes_raw:
                if isinstance(item, dict):
                    try:
                        d = int(item.get("days"))
                    except Exception:
                        continue
                    if d > 0:
                        default_days = d
                        break

        plan_config_dir.mkdir(parents=True, exist_ok=True)
        jobs = []
        for idx, pair in enumerate(pairs, start=1):
            timeframe = pair["timeframe"]
            symbol = pair["symbol"]
            days = int(td_map.get(timeframe, default_days))

            cfg_payload = json.loads(json.dumps(template_config, ensure_ascii=False))
            cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": days}]
            cfg_payload["trade_symbols"] = [symbol]

            cfg_name = f"cron_{idx:03d}_{_slug_text(timeframe)}_{_slug_text(symbol)}.json"
            cfg_path = plan_config_dir / cfg_name
            cfg_path.write_text(json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            job: Dict[str, Any] = {
                "name": f"cron-{idx:03d}-{_slug_text(timeframe)}-{_slug_text(symbol)}",
                "workflow": workflow,
                "config": str(cfg_path),
            }
            if workflow == "run" and mode is not None:
                job["mode"] = mode
            if workers is not None:
                job["workers"] = workers
            jobs.append(job)

        plan_payload = {
            "generated_utc": _utc_now_iso(),
            "source_registry": str(registry_path),
            "source_template_config": str(template_config_path),
            "job_count": len(jobs),
            "jobs": jobs,
        }
        plan_out.parent.mkdir(parents=True, exist_ok=True)
        plan_out.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result["plan_jobs"] = len(jobs)
        print(f"[cron:plan] generated {len(jobs)} jobs → {plan_out}")
    except Exception as exc:
        result["error"] = f"plan failed: {exc}"
        print(f"[cron:plan] ERROR: {exc}")
        return result

    # If no jobs, skip batch and go straight to report
    if not jobs:
        print("[cron:plan] no untested pairs — skipping batch")
        result["batch_ok"] = True
    else:
        # --- 2. Batch ----------------------------------------------------------
        try:
            parsed_jobs = _parse_batch_jobs(plan_payload, cwd, plan_out, workers)
            state = _load_batch_state(batch_state_path)

            if parallel_jobs > 1:
                failed = _run_batch_jobs_parallel(
                    jobs=parsed_jobs,
                    state=state,
                    state_path=batch_state_path,
                    parallel_jobs=parallel_jobs,
                    continue_on_error=continue_on_error,
                )
                result["batch_ok"] = not failed
            else:
                all_ok = True
                for idx, job_entry in enumerate(parsed_jobs, start=1):
                    lock = threading.Lock()
                    job_result = _run_batch_job_single(
                        idx=idx,
                        total=len(parsed_jobs),
                        job=job_entry,
                        state=state,
                        state_path=batch_state_path,
                        lock=lock,
                    )
                    if job_result["status"] == "failed":
                        all_ok = False
                        if not continue_on_error:
                            break
                result["batch_ok"] = all_ok
            print(f"[cron:batch] completed {len(jobs)} jobs")
        except Exception as exc:
            result["error"] = f"batch failed: {exc}"
            print(f"[cron:batch] ERROR: {exc}")
            if not continue_on_error:
                return result
            # Still attempt report even if batch partial-failed
            result["batch_ok"] = False

    # --- 3. Report ---------------------------------------------------------
    try:
        from scripts.autowfo import cross_run

        artifacts_dir = cwd / "artifacts"
        if not artifacts_dir.exists():
            artifacts_dir.mkdir(parents=True, exist_ok=True)

        report_payload = cross_run.write_cross_run_reports(
            artifacts_dir=artifacts_dir,
            registry_path=registry_path,
            out_html_path=report_html_path,
            out_json_path=report_json_path,
            top_n=top_n,
        )
        result["top_entities"] = _extract_top_entities(report_payload, limit=max(1, int(top_n)))
        result["report_ok"] = True
        print(f"[cron:report] → {report_html_path}")
    except Exception as exc:
        result["error"] = f"report failed: {exc}"
        print(f"[cron:report] ERROR: {exc}")

    result["cycle_end_utc"] = _utc_now_iso()
    return result

