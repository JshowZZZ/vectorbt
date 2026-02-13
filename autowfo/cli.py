"""CLI entrypoint for AUTOWFO workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_path(base: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(
                f"config must be JSON or YAML (install PyYAML for YAML support): {path}"
            ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"config must decode to object: {path}")
    return payload


def _json_sha256(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_runtime_config(
    cwd: Path,
    config_path: Path,
    mode: Optional[str],
    workers: Optional[int],
) -> Path:
    artifacts_dir = cwd / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    config = _load_config(config_path)
    if mode:
        config["search_mode"] = mode
    if workers is not None:
        config["max_workers"] = int(workers)

    runtime_config_path = artifacts_dir / "sweep_config.json"
    runtime_config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return runtime_config_path


def _run_module(module_name: str, cwd: Path, env: Dict[str, str]) -> None:
    cmd = [sys.executable, "-m", module_name]
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def _run_workflow(
    cwd: Path,
    config_path: Path,
    workflow: str,
    mode: Optional[str] = None,
    workers: Optional[int] = None,
) -> None:
    if workflow not in {"run", "baseline"}:
        raise ValueError(f"Unsupported workflow: {workflow}")

    runtime_config_path = _write_runtime_config(
        cwd=cwd,
        config_path=config_path,
        mode=mode if workflow == "run" else None,
        workers=workers,
    )
    env = os.environ.copy()

    if workflow == "run":
        if mode:
            env["VBT_SWEEP_MODE"] = mode
        print(f"[autowfo] runtime_config={runtime_config_path}")
        print(f"[autowfo] mode={mode or 'config_default'} workers={workers or 'config_default'}")
        _run_module("scripts.run_btc_regime_sweep", cwd=cwd, env=env)
        return

    print(f"[autowfo] runtime_config={runtime_config_path}")
    print(f"[autowfo] baseline workers={workers or 'config_default'}")
    _run_module("scripts.run_autowfo_baseline", cwd=cwd, env=env)


def _cmd_run(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    _run_workflow(
        cwd=cwd,
        config_path=config_path,
        workflow="run",
        mode=args.mode,
        workers=args.workers,
    )
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    _run_workflow(
        cwd=cwd,
        config_path=config_path,
        workflow="baseline",
        mode=None,
        workers=args.workers,
    )
    return 0


def _parse_batch_jobs(
    plan_payload: Dict[str, Any],
    cwd: Path,
    plan_path: Path,
    workers_override: Optional[int],
) -> List[Dict[str, Any]]:
    jobs_raw = plan_payload.get("jobs")
    if not isinstance(jobs_raw, list) or not jobs_raw:
        raise ValueError("batch plan must contain non-empty 'jobs' list")

    defaults = plan_payload.get("defaults")
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ValueError("batch plan 'defaults' must be object when provided")

    jobs: List[Dict[str, Any]] = []
    for idx, raw in enumerate(jobs_raw, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"batch job #{idx} must be object")

        name = str(raw.get("name") or f"job-{idx}")
        workflow = str(raw.get("workflow", defaults.get("workflow", "baseline"))).lower()
        if workflow not in {"run", "baseline"}:
            raise ValueError(f"batch job '{name}': workflow must be run|baseline")

        config_value = raw.get("config", defaults.get("config"))
        if not config_value:
            raise ValueError(f"batch job '{name}': missing config path")
        config_path = Path(str(config_value))
        if not config_path.is_absolute():
            config_path = (plan_path.parent / config_path).resolve()

        job_cwd_raw = raw.get("cwd", defaults.get("cwd"))
        if job_cwd_raw:
            job_cwd = Path(str(job_cwd_raw))
            if not job_cwd.is_absolute():
                job_cwd = (cwd / job_cwd).resolve()
        else:
            job_cwd = cwd

        mode_raw = raw.get("mode", defaults.get("mode"))
        mode = None if mode_raw in (None, "") else str(mode_raw).lower()
        if workflow == "baseline" and mode is not None:
            raise ValueError(f"batch job '{name}': mode override only valid for workflow=run")
        if workflow == "run" and mode not in {None, "combo", "refine"}:
            raise ValueError(f"batch job '{name}': mode must be combo|refine when provided")

        worker_raw = workers_override if workers_override is not None else raw.get("workers", defaults.get("workers"))
        workers = None if worker_raw in (None, "") else int(worker_raw)
        if workers is not None and workers <= 0:
            raise ValueError(f"batch job '{name}': workers must be > 0")

        jobs.append(
            {
                "name": name,
                "workflow": workflow,
                "config_path": config_path,
                "cwd": job_cwd,
                "mode": mode,
                "workers": workers,
            }
        )
    return jobs


def _preflight_batch_jobs(jobs: List[Dict[str, Any]], min_free_gb: float) -> None:
    missing_configs = [str(job["config_path"]) for job in jobs if not job["config_path"].exists()]
    if missing_configs:
        msg = "\n".join(missing_configs)
        raise FileNotFoundError(f"batch preflight failed: missing config files\n{msg}")

    missing_cwds = [str(job["cwd"]) for job in jobs if not job["cwd"].exists()]
    if missing_cwds:
        msg = "\n".join(missing_cwds)
        raise FileNotFoundError(f"batch preflight failed: missing cwd paths\n{msg}")

    if min_free_gb <= 0:
        return

    min_free_bytes = int(min_free_gb * (1024**3))
    for cwd in sorted({job["cwd"] for job in jobs}):
        usage = shutil.disk_usage(str(cwd))
        if usage.free < min_free_bytes:
            free_gb = usage.free / (1024**3)
            raise RuntimeError(
                f"batch preflight failed: insufficient disk at {cwd} ({free_gb:.2f}GB < {min_free_gb:.2f}GB)"
            )


def _load_batch_state(path: Path) -> Dict[str, Any]:
    default_state: Dict[str, Any] = {
        "version": 1,
        "created_utc": _utc_now_iso(),
        "updated_utc": _utc_now_iso(),
        "seen_keys": {},
        "history": [],
    }
    if not path.exists():
        return default_state

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_state

    if not isinstance(payload, dict):
        return default_state
    if not isinstance(payload.get("seen_keys"), dict):
        payload["seen_keys"] = {}
    if not isinstance(payload.get("history"), list):
        payload["history"] = []
    payload.setdefault("version", 1)
    payload.setdefault("created_utc", _utc_now_iso())
    payload["updated_utc"] = _utc_now_iso()
    return payload


def _write_batch_state(path: Path, payload: Dict[str, Any]) -> None:
    payload["updated_utc"] = _utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_run_label(cwd: Path) -> Optional[str]:
    runs_dir = cwd / "artifacts" / "runs"
    if not runs_dir.exists():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest.name


def _list_run_labels(cwd: Path) -> Set[str]:
    runs_dir = cwd / "artifacts" / "runs"
    if not runs_dir.exists():
        return set()
    return {p.name for p in runs_dir.iterdir() if p.is_dir()}


def _resolve_gate_c_target_mode(
    *,
    workflow: str,
    mode: Optional[str],
    target_mode: Optional[str],
    config_payload: Dict[str, Any],
) -> str:
    if target_mode:
        mode_value = str(target_mode).strip().lower()
    elif workflow == "baseline":
        mode_value = "refine"
    elif mode:
        mode_value = str(mode).strip().lower()
    else:
        mode_value = str(config_payload.get("search_mode", "combo")).strip().lower()
    if mode_value not in {"combo", "refine"}:
        raise ValueError(f"unsupported target mode for Gate C: {mode_value}")
    return mode_value


def _resolve_gate_c_run_dir(cwd: Path, run_label: str, target_mode: str) -> Path:
    run_root = cwd / "artifacts" / "runs" / run_label
    mode_dir = run_root / target_mode
    if mode_dir.exists() and mode_dir.is_dir():
        return mode_dir
    if run_root.exists() and run_root.is_dir():
        return run_root
    raise FileNotFoundError(f"run directory not found for label={run_label} mode={target_mode}")


def _resolve_top10_csv_path(run_dir: Path, run_id: str) -> Path:
    if run_id:
        run_scoped = run_dir / f"param_sweep_top10_{run_id}.csv"
        if run_scoped.exists():
            return run_scoped

    candidates = sorted(run_dir.glob("param_sweep_top10_*.csv"))
    if candidates:
        return candidates[-1]

    plain = run_dir / "param_sweep_top10.csv"
    if plain.exists():
        return plain
    raise FileNotFoundError(f"top-N csv not found under {run_dir}")


def _compute_job_key(job: Dict[str, Any]) -> str:
    config_payload = _load_config(job["config_path"])
    key_payload = {
        "workflow": job["workflow"],
        "mode": job.get("mode"),
        "workers": job.get("workers"),
        "config_sha256": _json_sha256(config_payload),
    }
    return _json_sha256(key_payload)


def _cmd_batch(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        raise FileNotFoundError(f"batch plan not found: {plan_path}")

    state_path = _resolve_path(cwd, args.state)
    plan_payload = _load_config(plan_path)
    jobs = _parse_batch_jobs(plan_payload, cwd=cwd, plan_path=plan_path, workers_override=args.workers)
    _preflight_batch_jobs(jobs, min_free_gb=float(args.min_free_gb))

    state = _load_batch_state(state_path)
    _write_batch_state(state_path, state)

    total = len(jobs)
    for idx, job in enumerate(jobs, start=1):
        job_key = _compute_job_key(job)
        label = f"[batch][{idx}/{total}] {job['name']}"

        if job_key in state["seen_keys"]:
            print(f"{label} skip (seen_key={job_key[:12]})")
            state["history"].append(
                {
                    "ts": _utc_now_iso(),
                    "status": "skipped_seen_key",
                    "job_key": job_key,
                    "job_name": job["name"],
                    "workflow": job["workflow"],
                    "config_path": str(job["config_path"]),
                }
            )
            _write_batch_state(state_path, state)
            continue

        print(
            f"{label} start workflow={job['workflow']} "
            f"config={job['config_path']} workers={job['workers'] or 'config_default'}"
        )
        before_label = _latest_run_label(job["cwd"])
        state["history"].append(
            {
                "ts": _utc_now_iso(),
                "status": "running",
                "job_key": job_key,
                "job_name": job["name"],
                "workflow": job["workflow"],
                "config_path": str(job["config_path"]),
            }
        )
        _write_batch_state(state_path, state)

        try:
            _run_workflow(
                cwd=job["cwd"],
                config_path=job["config_path"],
                workflow=job["workflow"],
                mode=job.get("mode"),
                workers=job.get("workers"),
            )
        except Exception as exc:
            state["history"].append(
                {
                    "ts": _utc_now_iso(),
                    "status": "failed",
                    "job_key": job_key,
                    "job_name": job["name"],
                    "workflow": job["workflow"],
                    "config_path": str(job["config_path"]),
                    "error": str(exc),
                }
            )
            _write_batch_state(state_path, state)
            print(f"{label} failed: {exc}")
            if args.continue_on_error:
                continue
            raise

        after_label = _latest_run_label(job["cwd"])
        run_label = after_label if after_label and after_label != before_label else None
        state["seen_keys"][job_key] = {
            "status": "done",
            "job_name": job["name"],
            "workflow": job["workflow"],
            "config_path": str(job["config_path"]),
            "mode": job.get("mode"),
            "workers": job.get("workers"),
            "finished_utc": _utc_now_iso(),
            "run_label": run_label,
        }
        state["history"].append(
            {
                "ts": _utc_now_iso(),
                "status": "done",
                "job_key": job_key,
                "job_name": job["name"],
                "workflow": job["workflow"],
                "config_path": str(job["config_path"]),
                "run_label": run_label,
            }
        )
        _write_batch_state(state_path, state)
        print(f"{label} done run_label={run_label or 'n/a'} seen_key={job_key[:12]}")

    print(f"[batch] finished jobs={total} seen_keys={len(state['seen_keys'])} state={state_path}")
    return 0


def _slug_text(value: str) -> str:
    text = str(value).strip()
    if not text:
        return "unknown"
    out_chars = []
    for ch in text:
        if ch.isalnum() or ch in {"-", "_"}:
            out_chars.append(ch)
        else:
            out_chars.append("-")
    slug = "".join(out_chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "unknown"


def _extract_registry_untested_pairs(registry_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    coverage = registry_payload.get("coverage")
    if not isinstance(coverage, dict):
        return []
    pairs = coverage.get("untested_pairs")
    if not isinstance(pairs, list):
        return []

    output: List[Dict[str, str]] = []
    seen = set()
    for raw in pairs:
        if not isinstance(raw, dict):
            continue
        timeframe = str(raw.get("timeframe", "")).strip()
        symbol = str(raw.get("symbol", "")).strip()
        if not timeframe or not symbol:
            continue
        key = (timeframe, symbol)
        if key in seen:
            continue
        seen.add(key)
        output.append({"timeframe": timeframe, "symbol": symbol})
    return output


def _build_timeframe_days_map(
    registry_payload: Dict[str, Any],
    template_config: Dict[str, Any],
) -> Dict[str, int]:
    mapping: Dict[str, int] = {}

    runs = registry_payload.get("runs")
    if isinstance(runs, list):
        for entry in runs:
            if not isinstance(entry, dict):
                continue
            timeframes = entry.get("timeframes")
            if not isinstance(timeframes, list):
                continue
            for item in timeframes:
                if not isinstance(item, dict):
                    continue
                timeframe = str(item.get("timeframe", "")).strip()
                if not timeframe:
                    continue
                try:
                    days = int(item.get("days"))
                except Exception:
                    continue
                if days <= 0:
                    continue
                if timeframe not in mapping:
                    mapping[timeframe] = days

    template_timeframes = template_config.get("timeframes")
    if isinstance(template_timeframes, list):
        for item in template_timeframes:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            if not timeframe:
                continue
            try:
                days = int(item.get("days"))
            except Exception:
                continue
            if days <= 0:
                continue
            if timeframe not in mapping:
                mapping[timeframe] = days

    return mapping


def _cmd_plan(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    registry_path = _resolve_path(cwd, args.registry)
    template_config_path = _resolve_path(cwd, args.template_config)
    out_plan_path = _resolve_path(cwd, args.out_plan)
    out_config_dir = _resolve_path(cwd, args.out_config_dir)

    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    if not template_config_path.exists():
        raise FileNotFoundError(f"template config not found: {template_config_path}")

    registry_payload = _load_config(registry_path)
    template_config = _load_config(template_config_path)
    pairs = _extract_registry_untested_pairs(registry_payload)

    max_jobs = None if args.max_jobs in (None, 0) else int(args.max_jobs)
    if max_jobs is not None and max_jobs < 0:
        raise ValueError("max-jobs must be >= 0")
    if max_jobs is not None:
        pairs = pairs[:max_jobs]

    workflow = str(args.workflow).strip().lower()
    mode = None if args.mode in (None, "") else str(args.mode).strip().lower()
    if workflow not in {"run", "baseline"}:
        raise ValueError("workflow must be run or baseline")
    if workflow == "baseline" and mode is not None:
        raise ValueError("mode is only valid when workflow=run")
    if workflow == "run" and mode not in {None, "combo", "refine"}:
        raise ValueError("mode must be combo/refine when provided")

    workers = None
    if args.workers is not None:
        workers = int(args.workers)
        if workers <= 0:
            raise ValueError("workers must be > 0")

    timeframe_days = _build_timeframe_days_map(registry_payload, template_config)
    default_days = 60
    template_timeframes = template_config.get("timeframes")
    if isinstance(template_timeframes, list):
        for item in template_timeframes:
            if not isinstance(item, dict):
                continue
            try:
                d = int(item.get("days"))
            except Exception:
                continue
            if d > 0:
                default_days = d
                break

    out_config_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for idx, pair in enumerate(pairs, start=1):
        timeframe = pair["timeframe"]
        symbol = pair["symbol"]
        days = int(timeframe_days.get(timeframe, default_days))

        cfg_payload = json.loads(json.dumps(template_config, ensure_ascii=False))
        cfg_payload["timeframes"] = [{"timeframe": timeframe, "days": days}]
        cfg_payload["trade_symbols"] = [symbol]

        cfg_name = f"{idx:03d}_{_slug_text(timeframe)}_{_slug_text(symbol)}.json"
        cfg_path = out_config_dir / cfg_name
        cfg_path.write_text(json.dumps(cfg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        job = {
            "name": f"gap-{idx:03d}-{_slug_text(timeframe)}-{_slug_text(symbol)}",
            "workflow": workflow,
            "config": str(cfg_path),
        }
        if workflow == "run" and mode is not None:
            job["mode"] = mode
        if workers is not None:
            job["workers"] = workers
        jobs.append(job)

    out_plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_payload = {
        "generated_utc": _utc_now_iso(),
        "source_registry": str(registry_path),
        "source_template_config": str(template_config_path),
        "job_count": len(jobs),
        "jobs": jobs,
    }
    out_plan_path.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[plan] registry={registry_path}")
    print(f"[plan] template_config={template_config_path}")
    print(f"[plan] out_plan={out_plan_path}")
    print(f"[plan] out_config_dir={out_config_dir} jobs={len(jobs)}")
    if not jobs:
        print("[plan] no untested pairs found")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from scripts.autowfo import cross_run

    cwd = Path(args.cwd).resolve()
    artifacts_dir = _resolve_path(cwd, args.artifacts_dir)
    registry_path = _resolve_path(cwd, args.registry)
    out_html_path = _resolve_path(cwd, args.out_html)
    out_json_path = _resolve_path(cwd, args.out_json) if args.out_json else None

    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    if not artifacts_dir.exists():
        raise FileNotFoundError(f"artifacts dir not found: {artifacts_dir}")

    payload = cross_run.write_cross_run_reports(
        artifacts_dir=artifacts_dir,
        registry_path=registry_path,
        out_html_path=out_html_path,
        out_json_path=out_json_path,
        top_n=int(args.top_n),
    )
    summary = payload.get("summary", {})
    print(f"[report] registry={registry_path}")
    print(f"[report] artifacts={artifacts_dir}")
    print(f"[report] out_html={out_html_path}")
    if out_json_path is not None:
        print(f"[report] out_json={out_json_path}")
    print(
        "[report] runs={runs} symbols={symbols} timeframes={timeframes} coverage_pct={coverage}".format(
            runs=summary.get("total_runs", 0),
            symbols=summary.get("unique_symbols", 0),
            timeframes=summary.get("unique_timeframes", 0),
            coverage=summary.get("coverage_pct", 0),
        )
    )
    return 0


def _split_csv_fields(raw: Optional[str]) -> List[str]:
    if raw in (None, ""):
        return []
    return [part.strip() for part in str(raw).split(",") if part and str(part).strip()]


def _cmd_repro(args: argparse.Namespace) -> int:
    import pandas as pd

    from scripts.autowfo import reproducibility

    cwd = Path(args.cwd).resolve()
    reference_top = _resolve_path(cwd, args.reference_top)
    candidate_top = _resolve_path(cwd, args.candidate_top)
    out_json = _resolve_path(cwd, args.out_json)

    if not reference_top.exists():
        raise FileNotFoundError(f"reference top csv not found: {reference_top}")
    if not candidate_top.exists():
        raise FileNotFoundError(f"candidate top csv not found: {candidate_top}")

    identity_fields = _split_csv_fields(args.identity_fields) or list(reproducibility.DEFAULT_IDENTITY_FIELDS)
    metric_fields = _split_csv_fields(args.metric_fields) or list(reproducibility.DEFAULT_METRIC_FIELDS)

    reference_df = pd.read_csv(reference_top, low_memory=False)
    candidate_df = pd.read_csv(candidate_top, low_memory=False)
    payload = reproducibility.compare_top_n_stability(
        reference_df=reference_df,
        candidate_df=candidate_df,
        top_n=int(args.top_n),
        identity_fields=identity_fields,
        metric_fields=metric_fields,
        metric_abs_tolerance=float(args.metric_abs_tolerance),
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[repro] reference={reference_top}")
    print(f"[repro] candidate={candidate_top}")
    print(f"[repro] out_json={out_json}")
    print(
        "[repro] stable={stable} identity_match={identity_match} metric_match={metric_match} "
        "overlap_rows={overlap}/{top_n}".format(
            stable=payload.get("stable"),
            identity_match=payload.get("identity_match"),
            metric_match=payload.get("metric_match"),
            overlap=payload.get("overlap_rows", 0),
            top_n=payload.get("top_n", 0),
        )
    )
    return 0


def _cmd_gate_c(args: argparse.Namespace) -> int:
    import pandas as pd

    from scripts.autowfo import reproducibility

    cwd = Path(args.cwd).resolve()
    config_path = _resolve_path(cwd, args.config)
    out_json = _resolve_path(cwd, args.out_json)
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    config_payload = _load_config(config_path)
    workflow = str(args.workflow).strip().lower()
    if workflow not in {"run", "baseline"}:
        raise ValueError("workflow must be run or baseline")

    mode = None if args.mode in (None, "") else str(args.mode).strip().lower()
    if workflow == "baseline" and mode is not None:
        raise ValueError("mode override is only valid for workflow=run")
    if workflow == "run" and mode not in {None, "combo", "refine"}:
        raise ValueError("mode must be combo|refine when provided")

    workers = None if args.workers in (None, "") else int(args.workers)
    if workers is not None and workers <= 0:
        raise ValueError("workers must be > 0")

    target_mode = _resolve_gate_c_target_mode(
        workflow=workflow,
        mode=mode,
        target_mode=args.target_mode,
        config_payload=config_payload,
    )
    identity_fields = _split_csv_fields(args.identity_fields) or list(reproducibility.DEFAULT_IDENTITY_FIELDS)
    metric_fields = _split_csv_fields(args.metric_fields) or list(reproducibility.DEFAULT_METRIC_FIELDS)
    top_n = int(args.top_n)
    metric_abs_tolerance = float(args.metric_abs_tolerance)
    gate_label = str(args.label).strip() if args.label else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    run_records: List[Dict[str, Any]] = []
    for run_index in (1, 2):
        before_labels: Set[str] = set()
        if workflow == "baseline":
            before_labels = _list_run_labels(cwd)

        _run_workflow(
            cwd=cwd,
            config_path=config_path,
            workflow=workflow,
            mode=mode if workflow == "run" else None,
            workers=workers,
        )

        run_label = ""
        if workflow == "baseline":
            after_labels = _list_run_labels(cwd)
            new_labels = sorted(after_labels - before_labels)
            run_label = new_labels[-1] if new_labels else (_latest_run_label(cwd) or "")
            if not run_label:
                raise RuntimeError("unable to determine run label after baseline workflow execution")
            run_dir = _resolve_gate_c_run_dir(cwd, run_label, target_mode=target_mode)
        else:
            run_dir = (cwd / "artifacts").resolve()

        run_metadata_path = run_dir / "run_metadata.json"
        if not run_metadata_path.exists():
            raise FileNotFoundError(f"run metadata not found: {run_metadata_path}")

        run_metadata = _load_config(run_metadata_path)
        run_id = str(run_metadata.get("run_id", "")).strip()
        top_csv = _resolve_top10_csv_path(run_dir, run_id=run_id)
        schema_validation = reproducibility.validate_run_artifact_schema(run_dir)

        run_records.append(
            {
                "run_index": run_index,
                "run_label": run_label,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "top_csv": str(top_csv),
                "run_metadata_path": str(run_metadata_path),
                "schema_validation": schema_validation,
            }
        )

    reference_df = pd.read_csv(run_records[0]["top_csv"], low_memory=False)
    candidate_df = pd.read_csv(run_records[1]["top_csv"], low_memory=False)
    reproducibility_payload = reproducibility.compare_top_n_stability(
        reference_df=reference_df,
        candidate_df=candidate_df,
        top_n=top_n,
        identity_fields=identity_fields,
        metric_fields=metric_fields,
        metric_abs_tolerance=metric_abs_tolerance,
    )

    schema_valid = all(bool(record["schema_validation"].get("valid")) for record in run_records)
    gate_c_passed = bool(reproducibility_payload.get("stable")) and schema_valid

    report_payload: Dict[str, Any] = {
        "generated_utc": _utc_now_iso(),
        "gate_c_label": gate_label,
        "config_path": str(config_path),
        "workflow": workflow,
        "mode": mode,
        "target_mode": target_mode,
        "workers": workers,
        "top_n": top_n,
        "metric_abs_tolerance": metric_abs_tolerance,
        "identity_fields": identity_fields,
        "metric_fields": metric_fields,
        "runs": run_records,
        "schema_valid": schema_valid,
        "reproducibility": reproducibility_payload,
        "gate_c_passed": gate_c_passed,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gate-c] config={config_path}")
    print(f"[gate-c] workflow={workflow} mode={mode or 'config_default'} target_mode={target_mode}")
    print(
        f"[gate-c] run1={run_records[0]['run_label'] or 'n/a'} "
        f"run_dir={run_records[0]['run_dir']} top={run_records[0]['top_csv']}"
    )
    print(
        f"[gate-c] run2={run_records[1]['run_label'] or 'n/a'} "
        f"run_dir={run_records[1]['run_dir']} top={run_records[1]['top_csv']}"
    )
    print(f"[gate-c] out_json={out_json}")
    print(
        "[gate-c] schema_valid={schema_valid} stable={stable} gate_c_passed={gate_c_passed} "
        "overlap_rows={overlap}/{top_n}".format(
            schema_valid=schema_valid,
            stable=reproducibility_payload.get("stable"),
            gate_c_passed=gate_c_passed,
            overlap=reproducibility_payload.get("overlap_rows", 0),
            top_n=top_n,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autowfo", description="AUTOWFO one-command workflows")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one sweep end-to-end")
    run_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    run_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default=None,
        help="Override search mode",
    )
    run_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    run_parser.add_argument("--cwd", default=".", help="Working directory")
    run_parser.set_defaults(handler=_cmd_run)

    baseline_parser = subparsers.add_parser("baseline", help="Run combo+refine baseline workflow")
    baseline_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    baseline_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    baseline_parser.add_argument("--cwd", default=".", help="Working directory")
    baseline_parser.set_defaults(handler=_cmd_baseline)

    batch_parser = subparsers.add_parser("batch", help="Run multi-config batch plan sequentially")
    batch_parser.add_argument("--plan", required=True, help="Path to batch plan (JSON/YAML)")
    batch_parser.add_argument("--workers", type=int, default=None, help="Global workers override for all jobs")
    batch_parser.add_argument("--cwd", default=".", help="Working directory")
    batch_parser.add_argument(
        "--state",
        default="artifacts/batch_state.json",
        help="Path to batch state JSON used for crash-safe resume",
    )
    batch_parser.add_argument(
        "--min-free-gb",
        type=float,
        default=20.0,
        help="Preflight minimum free disk (GB); set 0 to disable",
    )
    batch_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue remaining jobs if one job fails",
    )
    batch_parser.set_defaults(handler=_cmd_batch)

    plan_parser = subparsers.add_parser("plan", help="Generate batch plan from run registry coverage gaps")
    plan_parser.add_argument(
        "--registry",
        default="artifacts/run_registry.json",
        help="Path to run registry JSON",
    )
    plan_parser.add_argument(
        "--template-config",
        default="artifacts/sweep_config.json",
        help="Template config used to build per-gap configs",
    )
    plan_parser.add_argument(
        "--out-plan",
        default="artifacts/batch_plan.auto.json",
        help="Output path for generated batch plan JSON",
    )
    plan_parser.add_argument(
        "--out-config-dir",
        default="artifacts/planned_configs",
        help="Output directory for generated per-job config JSON files",
    )
    plan_parser.add_argument(
        "--max-jobs",
        type=int,
        default=0,
        help="Limit number of planned jobs (0 means no limit)",
    )
    plan_parser.add_argument(
        "--workflow",
        choices=["run", "baseline"],
        default="baseline",
        help="Workflow type to use in generated batch jobs",
    )
    plan_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default=None,
        help="Mode for workflow=run",
    )
    plan_parser.add_argument("--workers", type=int, default=None, help="Optional workers value for each generated job")
    plan_parser.add_argument("--cwd", default=".", help="Working directory")
    plan_parser.set_defaults(handler=_cmd_plan)

    report_parser = subparsers.add_parser("report", help="Generate cross-run dashboard report from run registry")
    report_parser.add_argument(
        "--registry",
        default="artifacts/run_registry.json",
        help="Path to run registry JSON",
    )
    report_parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Artifacts root directory",
    )
    report_parser.add_argument(
        "--out-html",
        default="artifacts/cross_run_report.html",
        help="Output path for cross-run HTML report",
    )
    report_parser.add_argument(
        "--out-json",
        default="artifacts/cross_run_report.json",
        help="Output path for cross-run JSON payload (set empty to disable)",
    )
    report_parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Top-N rows for leaderboard and combo-stability views",
    )
    report_parser.add_argument("--cwd", default=".", help="Working directory")
    report_parser.set_defaults(handler=_cmd_report)

    repro_parser = subparsers.add_parser(
        "repro",
        help="Compare two top-N CSV artifacts for reproducibility stability",
    )
    repro_parser.add_argument("--reference-top", required=True, help="Reference top-N CSV path")
    repro_parser.add_argument("--candidate-top", required=True, help="Candidate top-N CSV path")
    repro_parser.add_argument(
        "--out-json",
        default="artifacts/reproducibility_report.json",
        help="Output path for reproducibility JSON report",
    )
    repro_parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Top-N rows to compare",
    )
    repro_parser.add_argument(
        "--metric-abs-tolerance",
        type=float,
        default=1e-9,
        help="Absolute tolerance used for metric drift checks",
    )
    repro_parser.add_argument(
        "--identity-fields",
        default="",
        help="Comma-separated identity fields (default uses built-in identity schema)",
    )
    repro_parser.add_argument(
        "--metric-fields",
        default="",
        help="Comma-separated metric fields (default uses built-in reproducibility metrics)",
    )
    repro_parser.add_argument("--cwd", default=".", help="Working directory")
    repro_parser.set_defaults(handler=_cmd_repro)

    gate_c_parser = subparsers.add_parser(
        "gate-c",
        help="Run Gate C reproducibility workflow (dual run + schema validation + top-N comparison)",
    )
    gate_c_parser.add_argument("--config", required=True, help="Path to experiment config (JSON/YAML)")
    gate_c_parser.add_argument(
        "--workflow",
        choices=["run", "baseline"],
        default="run",
        help="Workflow to execute twice for reproducibility checks",
    )
    gate_c_parser.add_argument(
        "--mode",
        choices=["combo", "refine"],
        default=None,
        help="Optional mode override (workflow=run only)",
    )
    gate_c_parser.add_argument(
        "--target-mode",
        choices=["combo", "refine"],
        default=None,
        help="Artifact mode directory used for schema/top-N checks (default: run->mode/config, baseline->refine)",
    )
    gate_c_parser.add_argument("--workers", type=int, default=None, help="Override max_workers")
    gate_c_parser.add_argument(
        "--label",
        default="",
        help="Optional Gate C report label",
    )
    gate_c_parser.add_argument(
        "--out-json",
        default="artifacts/reproducibility/gate_c_report.json",
        help="Output path for Gate C report JSON",
    )
    gate_c_parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Top-N rows to compare",
    )
    gate_c_parser.add_argument(
        "--metric-abs-tolerance",
        type=float,
        default=1e-9,
        help="Absolute tolerance used for metric drift checks",
    )
    gate_c_parser.add_argument(
        "--identity-fields",
        default="",
        help="Comma-separated identity fields (default uses built-in identity schema)",
    )
    gate_c_parser.add_argument(
        "--metric-fields",
        default="",
        help="Comma-separated metric fields (default uses built-in reproducibility metrics)",
    )
    gate_c_parser.add_argument("--cwd", default=".", help="Working directory")
    gate_c_parser.set_defaults(handler=_cmd_gate_c)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))
