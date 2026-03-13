"""Experiment CRUD handlers for control_panel."""

from __future__ import annotations

import json
import re
import sys as _sys
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from autowfo.analytics import AnalyticsStore
from autowfo.artifact_store import ArtifactStore
from autowfo.discovery_loop import DiscoveryLoop
from autowfo.experiment import Experiment
from autowfo.notifier import NotificationEvent, notify, should_trigger_pnl_threshold
from autowfo.paper_position import PaperPositionStore
from autowfo.report_export import export_html_report
from autowfo.scheduler import ExperimentQueue, SchedulerConfig

EXPERIMENT_CONFIG_PATH_RE = re.compile(r"^/experiments/(?P<experiment_id>[^/]+)/config\.json$")
EXPERIMENT_RUN_PATH_RE = re.compile(r"^/experiments/(?P<experiment_id>[^/]+)/run$")
EXPERIMENT_QUEUE_PATH_RE = re.compile(r"^/experiments/queue$")
DISCOVERY_TICK_PATH_RE = re.compile(r"^/discovery/tick$")
EXPERIMENT_DELETE_PATH_RE = re.compile(r"^/experiments/(?P<experiment_id>[^/]+)$")
EXPERIMENT_RUNS_LIST_PATH_RE = re.compile(r"^/experiments/(?P<experiment_id>[^/]+)/runs\.json$")
EXPERIMENT_RUN_RESULTS_PATH_RE = re.compile(
    r"^/experiments/(?P<experiment_id>[^/]+)/runs/(?P<run_id>[^/]+)/results\.json$"
)
ANALYTICS_LEADERBOARD_PATH_RE = re.compile(r"^/analytics/leaderboard\.json$")
ANALYTICS_BEST_PATH_RE = re.compile(r"^/analytics/best\.json$")
ANALYTICS_COVERAGE_MAP_PATH_RE = re.compile(r"^/analytics/coverage-map\.json$")
ANALYTICS_GROWTH_PATH_RE = re.compile(r"^/analytics/growth\.json$")
ANALYTICS_REPORT_HTML_PATH_RE = re.compile(r"^/analytics/report\.html$")
SCHEDULER_STATUS_PATH_RE = re.compile(r"^/scheduler/status\.json$")
SCHEDULER_STOP_PATH_RE = re.compile(r"^/scheduler/stop$")
PAPER_POSITIONS_PATH_RE = re.compile(r"^/paper/positions\.json$")
PAPER_PORTFOLIO_PATH_RE = re.compile(r"^/paper/portfolio\.json$")
PAPER_OPEN_PATH_RE = re.compile(r"^/paper/open$")
PAPER_CLOSE_PATH_RE = re.compile(r"^/paper/close$")


def _cp():
    return _sys.modules.get("autowfo.control_panel.server")


def _runtime():
    cp = _cp()
    return getattr(cp, "RUNTIME", None) if cp is not None else None


def _paths():
    runtime = _runtime()
    return runtime.paths if runtime is not None else None


def _scheduler_runtime():
    runtime = _runtime()
    return runtime.scheduler if runtime is not None else None


def _experiments_root() -> Path:
    paths = _paths()
    return (paths.artifacts if paths is not None else Path("artifacts")) / "experiments"


def _experiment_dir(experiment_id: str) -> Path:
    return _experiments_root() / experiment_id


def _experiment_config_path(experiment_id: str) -> Path:
    return _experiment_dir(experiment_id) / "config.json"


def _artifact_store(experiment_id: str) -> ArtifactStore:
    paths = _paths()
    return ArtifactStore(experiment_id, base_dir=paths.artifacts if paths is not None else Path("artifacts"))


def _analytics_store() -> AnalyticsStore:
    paths = _paths()
    return AnalyticsStore((paths.artifacts if paths is not None else Path("artifacts")) / "analytics.duckdb")


def _scheduler_config_path() -> Path:
    paths = _paths()
    return (paths.artifacts if paths is not None else Path("artifacts")) / "scheduler.json"


def _scheduler_queue_path() -> Path:
    paths = _paths()
    return (paths.artifacts if paths is not None else Path("artifacts")) / "scheduler_queue.json"


def _paper_positions_path() -> Path:
    paths = _paths()
    return (paths.artifacts if paths is not None else Path("artifacts")) / "paper_positions.json"


def _paper_latest_prices_path() -> Path:
    paths = _paths()
    return (paths.artifacts if paths is not None else Path("artifacts")) / "paper_latest_prices.json"


def _notifier_config_path() -> Path:
    paths = _paths()
    return (paths.artifacts if paths is not None else Path("artifacts")) / "notifier_config.json"


def _scheduler_queue() -> ExperimentQueue:
    cfg = SchedulerConfig.from_file(_scheduler_config_path())
    return ExperimentQueue(queue_path=_scheduler_queue_path(), config=cfg)


def _paper_position_store() -> PaperPositionStore:
    return PaperPositionStore(_paper_positions_path())


def _scheduler_is_running() -> bool:
    scheduler = _scheduler_runtime()
    if scheduler is None:
        return False
    return bool(scheduler.snapshot().get("is_running"))


def _scheduler_priority(priority: Any, queue: ExperimentQueue) -> str:
    raw = str(priority or "").strip()
    if raw and raw in queue.config.priority_order:
        return raw
    if queue.config.priority_order:
        return queue.config.priority_order[0]
    return "discovery"


def _normalize_experiment_payload(payload: dict) -> tuple[dict, str, bool]:
    if not isinstance(payload, dict):
        payload = {}
    exp_cfg = payload.get("experiment_config")
    if isinstance(exp_cfg, dict):
        config = dict(exp_cfg)
    else:
        config = dict(payload)
        config.pop("priority", None)
        config.pop("auto_start", None)
    priority = str(payload.get("priority", "")).strip()
    auto_start_raw = str(payload.get("auto_start", "0")).strip().lower()
    auto_start = auto_start_raw in {"1", "true", "yes", "on"}
    return config, priority, auto_start


def _default_start_date() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()


def _scheduler_set_state(*, running: bool, last_error: str | None = None) -> None:
    scheduler = _scheduler_runtime()
    if scheduler is None:
        return
    scheduler.mark(
        running=running,
        last_run_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        last_error=last_error,
    )


def _execute_scheduled_experiment(item: dict) -> dict:
    from autowfo.data_multi import load_experiment_data
    from autowfo.experiment_runner import ExperimentRunner

    exp_cfg = item.get("experiment_config")
    if not isinstance(exp_cfg, dict):
        raise ValueError("queued item missing experiment_config")
    experiment = Experiment.from_dict(exp_cfg)
    config_path = _experiment_config_path(experiment.experiment_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    experiment.save(config_path)

    start_date = str(item.get("start_date") or exp_cfg.get("start_date") or "").strip() or _default_start_date()
    end_date = str(item.get("end_date") or exp_cfg.get("end_date") or "").strip() or None
    trigger_ohlcv, action_ohlcv = load_experiment_data(
        experiment=experiment,
        start_date=start_date,
        end_date=end_date,
        cache_dir=_scheduler_queue_path().parent / "ohlcv",
    )

    runner = ExperimentRunner(
        experiment=experiment,
        trigger_ohlcv=trigger_ohlcv,
        action_ohlcv=action_ohlcv,
        artifact_store=_artifact_store(experiment.experiment_id),
        analytics_store=_analytics_store(),
    )
    run_result = runner.run()
    return {
        "experiment_id": experiment.experiment_id,
        "run_id": run_result.run_id,
        "n_combos": run_result.n_combos,
        "n_completed": run_result.n_completed,
        "n_errors": run_result.n_errors,
    }


def _scheduler_run_once() -> dict:
    queue = _scheduler_queue()
    item = queue.pop()
    if item is None:
        return {"processed": False, "ok": True, "item": None}

    _scheduler_set_state(running=True)
    try:
        result = _execute_scheduled_experiment(item)
        _scheduler_set_state(running=False, last_error="")
        return {"processed": True, "ok": True, "item": item, "result": result}
    except Exception as exc:
        _scheduler_set_state(running=False, last_error=str(exc))
        return {
            "processed": True,
            "ok": False,
            "item": item,
            "error": str(exc),
        }


def _scheduler_worker_loop() -> None:
    scheduler = _scheduler_runtime()
    if scheduler is None:
        return
    while True:
        if scheduler.stop_event.is_set():
            break
        outcome = _scheduler_run_once()
        if not outcome.get("processed"):
            break


def _scheduler_start_worker() -> bool:
    scheduler = _scheduler_runtime()
    if scheduler is None:
        return False
    with scheduler.thread_lock:
        if scheduler.thread is not None and scheduler.thread.is_alive():
            return False
        scheduler.stop_event.clear()
        scheduler.thread = threading.Thread(
            target=_scheduler_worker_loop,
            name="autowfo-scheduler-worker",
            daemon=True,
        )
        scheduler.thread.start()
        return True


def _scheduler_stop_worker(timeout_seconds: float = 5.0) -> dict:
    scheduler = _scheduler_runtime()
    if scheduler is None:
        return {"ok": True, "thread_alive": False, "joined": False}
    scheduler.stop_event.set()
    with scheduler.thread_lock:
        thread = scheduler.thread
    joined = False
    if thread is not None and thread.is_alive():
        thread.join(timeout=max(0.0, float(timeout_seconds)))
        joined = True
    thread_alive = bool(thread is not None and thread.is_alive())
    if not thread_alive:
        with scheduler.thread_lock:
            scheduler.thread = None
    _scheduler_set_state(running=False)
    return {
        "ok": not thread_alive,
        "thread_alive": thread_alive,
        "joined": joined,
    }


def _scheduler_runtime_status() -> dict:
    queue = _scheduler_queue()
    head = queue.peek() or {}
    runtime_status = _scheduler_runtime().snapshot() if _scheduler_runtime() is not None else {}
    return {
        "queue_depth": queue.size(),
        "next_experiment_id": str(head.get("experiment_id") or "") or None,
        "is_running": bool(runtime_status.get("is_running")),
        "last_run_utc": str(runtime_status.get("last_run_utc") or ""),
        "last_error": str(runtime_status.get("last_error") or ""),
    }


def _resolve_pool_config(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}
    inline = payload.get("pool_config")
    if isinstance(inline, dict):
        return dict(inline)

    raw_path = str(payload.get("pool_path") or payload.get("pool") or "").strip()
    paths = _paths()
    if raw_path:
        pool_path = Path(raw_path)
        if not pool_path.is_absolute():
            base_root = paths.root if paths is not None else Path.cwd().resolve()
            pool_path = (base_root / pool_path).resolve()
    else:
        pool_path = (paths.artifacts if paths is not None else Path("artifacts")) / "discovery_pool.json"

    if not pool_path.exists():
        raise FileNotFoundError(pool_path)
    pool_cfg = _safe_json_read(pool_path, None)
    if not isinstance(pool_cfg, dict):
        raise ValueError("pool config must be object")
    return pool_cfg


def _scheduler_reset_runtime_state() -> None:
    scheduler = _scheduler_runtime()
    if scheduler is None:
        return
    scheduler.reset(join_timeout=1.0)


def _safe_json_read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _parse_utc(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _infer_field_from_error(message: str) -> str:
    msg = str(message or "").strip()
    if not msg:
        return ""
    if "." in msg:
        return msg.split(" ", 1)[0]
    if "_" in msg:
        return msg.split(" ", 1)[0]
    return msg.split(" ", 1)[0]


def _collect_experiment_summary(exp_id: str, config: dict) -> dict:
    exp_dir = _experiment_dir(exp_id)
    runs_dir = exp_dir / "runs"
    run_ids = sorted([path.name for path in runs_dir.iterdir() if path.is_dir()]) if runs_dir.exists() else []
    last_run_utc = ""
    best_oos_sharpe = None
    latest_ts = None

    for run_id in run_ids:
        meta_path = runs_dir / run_id / "run_meta.json"
        if not meta_path.exists():
            continue
        meta = _safe_json_read(meta_path, {})
        if not isinstance(meta, dict):
            continue
        run_ts = (
            str(meta.get("last_run_utc", "")).strip()
            or str(meta.get("completed_utc", "")).strip()
            or str(meta.get("created_utc", "")).strip()
        )
        parsed_ts = _parse_utc(run_ts)
        if parsed_ts is not None and (latest_ts is None or parsed_ts > latest_ts):
            latest_ts = parsed_ts
            last_run_utc = run_ts
        sharpe_raw = meta.get("best_oos_sharpe")
        try:
            sharpe_val = float(sharpe_raw)
            if best_oos_sharpe is None or sharpe_val > best_oos_sharpe:
                best_oos_sharpe = sharpe_val
        except Exception:
            pass

    return {
        "experiment_id": exp_id,
        "description": str(config.get("description", "")),
        "mode": str(config.get("mode", "")),
        "runs": len(run_ids),
        "last_run_utc": last_run_utc,
        "best_oos_sharpe": best_oos_sharpe,
        "status": "idle",
    }


def _handle_experiments_list(handler):
    rows = []
    root = _experiments_root()
    if root.exists():
        for config_path in sorted(root.glob("*/config.json")):
            config = _safe_json_read(config_path, {})
            if not isinstance(config, dict):
                continue
            exp_id = str(config.get("experiment_id") or config_path.parent.name)
            rows.append(_collect_experiment_summary(exp_id, config))

    payload = {"experiments": rows, "total": len(rows)}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_experiments_create(handler):
    try:
        payload = handler._read_json_payload()
    except Exception:
        payload = {}
    try:
        experiment = Experiment.from_dict(payload)
    except ValueError as exc:
        message = str(exc)
        return handler._send(
            json.dumps({"error": message, "field": _infer_field_from_error(message)}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )

    config_path = _experiment_config_path(experiment.experiment_id)
    if config_path.exists():
        return handler._send(
            json.dumps({"error": "experiment already exists", "field": "experiment_id"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.CONFLICT,
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    experiment.save(config_path)
    return handler._send(
        json.dumps({"ok": True, "experiment_id": experiment.experiment_id}, ensure_ascii=False),
        "application/json; charset=utf-8",
    )


def _handle_experiment_config(handler, experiment_id: str):
    config_path = _experiment_config_path(experiment_id)
    if not config_path.exists():
        return handler._send(
            json.dumps({"error": "experiment not found"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )
    config = _safe_json_read(config_path, None)
    if not isinstance(config, dict):
        return handler._send(
            json.dumps({"error": "invalid experiment config"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    return handler._send(json.dumps(config, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_experiment_delete(handler, experiment_id: str):
    exp_dir = _experiment_dir(experiment_id)
    config_path = exp_dir / "config.json"
    if not config_path.exists():
        return handler._send(
            json.dumps({"error": "experiment not found"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )

    runs_dir = exp_dir / "runs"
    if runs_dir.exists() and any(runs_dir.iterdir()):
        return handler._send(
            json.dumps({"error": "experiment has runs, cannot delete"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.CONFLICT,
        )

    config_path.unlink(missing_ok=True)
    if runs_dir.exists():
        try:
            runs_dir.rmdir()
        except OSError:
            pass
    try:
        exp_dir.rmdir()
    except OSError:
        pass
    return handler._send(
        json.dumps({"ok": True, "experiment_id": experiment_id}, ensure_ascii=False),
        "application/json; charset=utf-8",
    )


def _handle_experiment_run(handler, experiment_id: str):
    config_path = _experiment_config_path(experiment_id)
    if not config_path.exists():
        return handler._send(
            json.dumps({"error": "experiment not found"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )

    try:
        payload = handler._read_json_payload()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    mode = str(payload.get("mode", "combo")).strip().lower() or "combo"
    workers = payload.get("workers")
    job_name = str(payload.get("name", f"exp-{experiment_id}")).strip() or f"exp-{experiment_id}"

    enqueue_payload = {
        "workflow": "run",
        "mode": mode,
        "workers": workers,
        "config": str(config_path),
        "name": job_name,
    }
    ok, message, job = _cp()._batch_enqueue(enqueue_payload)
    if not ok:
        return handler._send(
            json.dumps({"error": message}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )

    return handler._send(
        json.dumps(
            {"ok": True, "queued": True, "job_id": str(job.get("id", ""))},
            ensure_ascii=False,
        ),
        "application/json; charset=utf-8",
    )


def _handle_experiments_queue(handler):
    try:
        payload = handler._read_json_payload()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    config, priority_raw, auto_start = _normalize_experiment_payload(payload)
    try:
        experiment = Experiment.from_dict(config)
    except ValueError as exc:
        message = str(exc)
        return handler._send(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "invalid_experiment_config",
                    "message": message,
                    "error": message,
                    "field": _infer_field_from_error(message),
                },
                ensure_ascii=False,
            ),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )

    queue = _scheduler_queue()
    priority = _scheduler_priority(priority_raw, queue)
    queued = queue.add(dict(experiment.config), priority=priority)

    config_path = _experiment_config_path(experiment.experiment_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    experiment.save(config_path)

    started = _scheduler_start_worker() if auto_start else False
    payload_out = {
        "ok": True,
        "queued": bool(queued),
        "experiment_id": experiment.experiment_id,
        "priority": priority,
        "queue_depth": queue.size(),
        "worker_started": bool(started),
    }
    return handler._send(json.dumps(payload_out, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_discovery_tick(handler):
    try:
        payload = handler._read_json_payload()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        pool_config = _resolve_pool_config(payload)
    except FileNotFoundError:
        return handler._send(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "invalid_pool_config",
                    "message": "pool config not found",
                    "error": "pool config not found",
                },
                ensure_ascii=False,
            ),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )
    except Exception as exc:
        return handler._send(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "invalid_pool_config",
                    "message": str(exc),
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )

    loop = DiscoveryLoop(
        pool_config=pool_config,
        scheduler=_scheduler_queue(),
        analytics_store=_analytics_store(),
        experiments_root=_experiments_root(),
    )
    summary = loop.tick()
    auto_start_raw = str(payload.get("auto_start", "0")).strip().lower()
    auto_start = auto_start_raw in {"1", "true", "yes", "on"}
    started = _scheduler_start_worker() if auto_start else False
    out = {
        "ok": True,
        "tick": summary,
        "worker_started": bool(started),
    }
    return handler._send(json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")


def _coerce_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _coerce_float_or_none(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _handle_experiment_runs_list(handler, experiment_id: str):
    config_path = _experiment_config_path(experiment_id)
    if not config_path.exists():
        return handler._send(
            json.dumps({"error": "experiment not found"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )

    store = _artifact_store(experiment_id)
    rows = []
    for run_id in store.list_runs():
        try:
            meta = store.read_run_meta(run_id)
        except FileNotFoundError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        rows.append(
            {
                "run_id": run_id,
                "n_combos": _coerce_int(meta.get("n_combos", 0), 0),
                "n_completed": _coerce_int(meta.get("n_completed", 0), 0),
                "n_errors": _coerce_int(meta.get("n_errors", 0), 0),
                "best_oos_sharpe": _coerce_float_or_none(meta.get("best_oos_sharpe")),
                "duration_seconds": _coerce_float_or_none(meta.get("duration_seconds")),
            }
        )

    payload = {"experiment_id": experiment_id, "runs": rows, "total": len(rows)}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_experiment_run_results(handler, experiment_id: str, run_id: str):
    config_path = _experiment_config_path(experiment_id)
    if not config_path.exists():
        return handler._send(
            json.dumps({"error": "experiment not found"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )

    query = parse_qs(urlparse(handler.path).query)
    try:
        limit = int(query.get("limit", ["50"])[0])
    except Exception:
        limit = 50
    limit = max(1, limit)

    store = _artifact_store(experiment_id)
    try:
        results = store.query_run_results(run_id=run_id, order_by="wf_score", limit=limit)
    except FileNotFoundError:
        return handler._send(
            json.dumps({"error": "run not found"}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )

    projected = []
    for row in results:
        projected.append(
            {
                "combo_id": row.get("combo_id"),
                "direction": row.get("direction"),
                "indicator_params": row.get("indicator_params"),
                "condition_params": row.get("condition_params"),
                "risk_params": row.get("risk_params"),
                "oos_sharpe": row.get("oos_sharpe"),
                "oos_win_rate": row.get("oos_win_rate"),
                "oos_n_trades": row.get("oos_n_trades"),
                "wf_score": row.get("wf_score"),
            }
        )

    payload = {
        "run_id": run_id,
        "results": projected,
        "total": len(projected),
    }
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_scheduler_status(handler):
    payload = _scheduler_runtime_status()
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_paper_positions(handler):
    positions = _paper_position_store().list_positions()
    payload = {"positions": positions, "total": len(positions)}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_paper_portfolio(handler):
    latest_prices = _safe_json_read(_paper_latest_prices_path(), {})
    if not isinstance(latest_prices, dict):
        latest_prices = {}
    snapshot = _paper_position_store().portfolio_snapshot(latest_prices=latest_prices)
    return handler._send(json.dumps(snapshot, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_paper_open(handler):
    try:
        payload = handler._read_json_payload()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    store = _paper_position_store()
    try:
        record = store.open_position(
            signal_id=payload.get("signal_id"),
            experiment_id=payload.get("experiment_id"),
            open_price=payload.get("open_price"),
            open_ts=payload.get("open_ts"),
        )
    except ValueError as exc:
        return handler._send(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )
    return handler._send(
        json.dumps({"ok": True, "position": record}, ensure_ascii=False),
        "application/json; charset=utf-8",
    )


def _handle_paper_close(handler):
    try:
        payload = handler._read_json_payload()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    store = _paper_position_store()
    try:
        pnl_pct, record = store.close_position(
            signal_id=payload.get("signal_id"),
            close_price=payload.get("close_price"),
            close_ts=payload.get("close_ts"),
        )
    except ValueError as exc:
        return handler._send(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.BAD_REQUEST,
        )

    analytics_updated = False
    analytics_error = ""
    try:
        _analytics_store().add_paper_feedback(
            experiment_id=record.get("experiment_id"),
            pnl_pct=pnl_pct,
            close_ts=record.get("close_ts"),
        )
        analytics_updated = True
    except Exception as exc:
        analytics_error = str(exc)

    notify_result = {
        "ok": True,
        "sent": [],
        "skipped": [],
        "errors": [],
    }
    try:
        notify_result = notify(
            NotificationEvent.POSITION_CLOSED,
            {
                "signal_id": record.get("signal_id"),
                "experiment_id": record.get("experiment_id"),
                "close_ts": record.get("close_ts"),
                "pnl_pct": pnl_pct,
            },
            config_path=_notifier_config_path(),
        )
        if should_trigger_pnl_threshold(float(pnl_pct), config_path=_notifier_config_path()):
            notify(
                NotificationEvent.PNL_THRESHOLD_HIT,
                {
                    "signal_id": record.get("signal_id"),
                    "experiment_id": record.get("experiment_id"),
                    "close_ts": record.get("close_ts"),
                    "pnl_pct": pnl_pct,
                },
                config_path=_notifier_config_path(),
            )
    except Exception:
        notify_result = {
            "ok": False,
            "sent": [],
            "skipped": [],
            "errors": ["notify_failed"],
        }

    return handler._send(
        json.dumps(
            {
                "ok": True,
                "pnl_pct": pnl_pct,
                "position": record,
                "analytics_updated": analytics_updated,
                "analytics_error": analytics_error,
                "notified": bool(notify_result.get("ok", True)),
                "notify_result": notify_result,
            },
            ensure_ascii=False,
        ),
        "application/json; charset=utf-8",
    )


def _handle_scheduler_stop(handler):
    result = _scheduler_stop_worker(timeout_seconds=5.0)
    return handler._send(
        json.dumps(
            {
                "ok": bool(result.get("ok")),
                "thread_alive": bool(result.get("thread_alive")),
                "stopped": bool(not result.get("thread_alive")),
            },
            ensure_ascii=False,
        ),
        "application/json; charset=utf-8",
    )


def _handle_analytics_leaderboard(handler):
    query = parse_qs(urlparse(handler.path).query)
    try:
        limit = int(query.get("limit", ["20"])[0])
    except Exception:
        limit = 20
    limit = max(1, limit)

    try:
        rows = _analytics_store().query_indicator_leaderboard(limit=limit)
    except Exception:
        rows = []
    payload = {"indicators": rows, "total": len(rows)}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_analytics_best(handler):
    query = parse_qs(urlparse(handler.path).query)
    try:
        limit = int(query.get("limit", ["50"])[0])
    except Exception:
        limit = 50
    limit = max(1, limit)

    try:
        rows = _analytics_store().query_all_time_best(limit=limit)
    except Exception:
        rows = []
    payload = {"combos": rows, "total": len(rows)}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_analytics_coverage_map(handler):
    try:
        rows = _analytics_store().query_indicator_coverage_map()
    except Exception:
        rows = []
    payload = {"pairs": rows, "total": len(rows)}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_analytics_growth(handler):
    try:
        growth = _analytics_store().query_analytics_growth()
    except Exception:
        growth = {
            "total_experiments": 0,
            "total_runs": 0,
            "total_combos": 0,
            "leaderboard_size": 0,
        }
    payload = {"growth": growth}
    return handler._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def _handle_analytics_report_html(handler):
    out_path = _scheduler_queue_path().parent / "research_report.html"
    try:
        export_html_report(_analytics_store(), out_path)
        html = out_path.read_text(encoding="utf-8")
        return handler._send(html, "text/html; charset=utf-8")
    except Exception as exc:
        return handler._send(
            json.dumps({"error": str(exc)}, ensure_ascii=False),
            "application/json; charset=utf-8",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

