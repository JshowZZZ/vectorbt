"""Run AUTOWFO baseline sweep in two passes: combo then refine."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

from autowfo import baseline as autowfo_baseline


def _utc_now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _load_config_payload(path: Path) -> Dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _clean_temp_outputs(repo_root: Path) -> Dict[str, bool]:
    removed = {}
    for name in ("test_out.txt", "test_output.txt"):
        path = repo_root / name
        if path.exists() and path.is_file():
            path.unlink()
            removed[name] = True
        else:
            removed[name] = False
    return removed


def _run_sweep(repo_root: Path, mode: str) -> None:
    env = os.environ.copy()
    env["VBT_SWEEP_MODE"] = mode
    cmd = [sys.executable, "-m", "autowfo.run_btc_regime_sweep"]
    subprocess.run(cmd, cwd=str(repo_root), env=env, check=True)


def _run_pass(repo_root: Path, artifacts_dir: Path, pass_dir: Path, mode: str) -> Tuple[str, Dict[str, object]]:
    before = autowfo_baseline._list_artifact_files(artifacts_dir)
    _run_sweep(repo_root, mode)
    after = autowfo_baseline._list_artifact_files(artifacts_dir)
    run_id = autowfo_baseline._extract_new_run_id(before, after)
    if run_id is None:
        run_id = autowfo_baseline._resolve_run_id_from_latest(artifacts_dir)
    if run_id is None:
        raise RuntimeError(f"Unable to detect run_id after {mode} sweep")

    copied = autowfo_baseline._copy_run_outputs(artifacts_dir, pass_dir, run_id)
    top10_df = autowfo_baseline._read_top10_for_run(pass_dir, run_id)
    snapshot = autowfo_baseline._quality_snapshot(top10_df)
    snapshot["run_id"] = run_id
    snapshot["mode"] = mode
    snapshot["copied"] = copied
    run_status = autowfo_baseline._read_run_status(pass_dir)
    snapshot["run_total"] = int(run_status.get("total", 0)) if run_status else 0
    snapshot["run_done"] = int(run_status.get("done", 0)) if run_status else 0
    snapshot["run_skipped"] = int(run_status.get("skipped", 0)) if run_status else 0
    snapshot["run_stage"] = run_status.get("stage") if run_status else None
    autowfo_baseline._write_json(pass_dir / "quality_snapshot.json", snapshot)
    return run_id, snapshot


def main() -> None:
    repo_root = Path.cwd().resolve()
    artifacts_dir = repo_root / "artifacts"
    config_path = artifacts_dir / "sweep_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config: {config_path}")
    config_payload = _load_config_payload(config_path)

    run_label = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_root = artifacts_dir / "runs" / run_label
    combo_dir = run_root / "combo"
    refine_dir = run_root / "refine"
    combo_dir.mkdir(parents=True, exist_ok=True)
    refine_dir.mkdir(parents=True, exist_ok=True)

    removed = _clean_temp_outputs(repo_root)
    snapshot_path = run_root / "sweep_config.snapshot.json"
    snapshot_path.write_bytes(config_path.read_bytes())

    manifest = {
        "run_label": run_label,
        "started_utc": _utc_now_iso(),
        "config_snapshot": str(snapshot_path.relative_to(repo_root)).replace("\\", "/"),
        "removed_temp_files": removed,
        "passes": [],
        "warnings": [],
    }
    autowfo_baseline._write_json(run_root / "manifest.json", manifest)

    combo_run_id, combo_snapshot = _run_pass(repo_root, artifacts_dir, combo_dir, "combo")
    manifest["passes"].append({"mode": "combo", "run_id": combo_run_id, "snapshot": combo_snapshot})
    autowfo_baseline._write_json(run_root / "manifest.json", manifest)

    # Ensure refine run gets a distinct run_id when script resolution is per-second.
    time.sleep(1.2)

    refine_run_id, refine_snapshot = _run_pass(repo_root, artifacts_dir, refine_dir, "refine")
    manifest["passes"].append({"mode": "refine", "run_id": refine_run_id, "snapshot": refine_snapshot})

    if int(refine_snapshot.get("run_total", 0)) == 0:
        warning = "refine pass processed zero candidates (run_total=0); comparison deltas may be non-informative"
        manifest["warnings"].append(warning)
        print(f"[baseline][warning] {warning}")

    comparison = autowfo_baseline._comparison_summary(combo_snapshot, refine_snapshot)
    autowfo_baseline._write_json(run_root / "comparison.json", comparison)

    refine_top10 = autowfo_baseline._read_top10_for_run(refine_dir, refine_run_id)
    trigger = autowfo_baseline._trigger_decision(refine_top10)
    autowfo_baseline._write_json(run_root / "trigger_decision.json", trigger)

    refine_combo_df = autowfo_baseline._read_combo_summary_for_run(refine_dir, refine_run_id)
    ranking_mode_comparison = autowfo_baseline._build_ranking_mode_comparison_report(
        combo_df=refine_combo_df,
        config_payload=config_payload,
        run_label=run_label,
        run_id=refine_run_id,
        generated_utc=_utc_now_iso(),
    )
    ranking_mode_comparison_json = run_root / "ranking_mode_comparison.json"
    ranking_mode_comparison_html = run_root / "ranking_mode_comparison.html"
    autowfo_baseline._write_json(ranking_mode_comparison_json, ranking_mode_comparison)
    ranking_mode_comparison_html.write_text(
        autowfo_baseline._render_ranking_mode_comparison_html(ranking_mode_comparison),
        encoding="utf-8",
    )

    manifest["ended_utc"] = _utc_now_iso()
    manifest["comparison"] = comparison
    manifest["trigger_decision"] = trigger
    manifest["ranking_mode_comparison"] = {
        "json": str(ranking_mode_comparison_json.relative_to(repo_root)).replace("\\", "/"),
        "html": str(ranking_mode_comparison_html.relative_to(repo_root)).replace("\\", "/"),
        "summary": ranking_mode_comparison.get("summary", {}),
    }
    autowfo_baseline._write_json(run_root / "manifest.json", manifest)

    print(f"[baseline] run_label={run_label}")
    print(f"[baseline] combo_run_id={combo_run_id}")
    print(f"[baseline] refine_run_id={refine_run_id}")
    print(f"[baseline] trigger_awf_002b_006={trigger['trigger_awf_002b_006']}")
    print(f"[baseline] ranking_mode_comparison={ranking_mode_comparison_json}")
    print(f"[baseline] output_dir={run_root}")


if __name__ == "__main__":
    main()

