"""Workflow and run-artifact helpers for AUTOWFO commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .core_utils import _load_config

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

