"""Gate command handler and parser wiring."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set


def add_gate_parser(subparsers: argparse._SubParsersAction[Any], cli_impl: Any) -> None:
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
    gate_c_parser.add_argument("--label", default="", help="Optional Gate C report label")
    gate_c_parser.add_argument(
        "--out-json",
        default="artifacts/reproducibility/gate_c_report.json",
        help="Output path for Gate C report JSON",
    )
    gate_c_parser.add_argument("--top-n", type=int, default=10, help="Top-N rows to compare")
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
    gate_c_parser.set_defaults(handler=cli_impl._cmd_gate_c)


def cmd_gate_c(args: argparse.Namespace, cli_impl: Any) -> int:
    import pandas as pd

    from autowfo import reproducibility

    cwd = Path(args.cwd).resolve()
    config_path = cli_impl._resolve_path(cwd, args.config)
    out_json = cli_impl._resolve_path(cwd, args.out_json)
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    config_payload = cli_impl._load_config(config_path)
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

    target_mode = cli_impl._resolve_gate_c_target_mode(
        workflow=workflow,
        mode=mode,
        target_mode=args.target_mode,
        config_payload=config_payload,
    )
    identity_fields = cli_impl._split_csv_fields(args.identity_fields) or list(reproducibility.DEFAULT_IDENTITY_FIELDS)
    metric_fields = cli_impl._split_csv_fields(args.metric_fields) or list(reproducibility.DEFAULT_METRIC_FIELDS)
    top_n = int(args.top_n)
    metric_abs_tolerance = float(args.metric_abs_tolerance)
    gate_label = str(args.label).strip() if args.label else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    run_records: List[Dict[str, Any]] = []
    for run_index in (1, 2):
        before_labels: Set[str] = set()
        if workflow == "baseline":
            before_labels = cli_impl._list_run_labels(cwd)

        cli_impl._run_workflow(
            cwd=cwd,
            config_path=config_path,
            workflow=workflow,
            mode=mode if workflow == "run" else None,
            workers=workers,
        )

        run_label = ""
        if workflow == "baseline":
            after_labels = cli_impl._list_run_labels(cwd)
            new_labels = sorted(after_labels - before_labels)
            run_label = new_labels[-1] if new_labels else (cli_impl._latest_run_label(cwd) or "")
            if not run_label:
                raise RuntimeError("unable to determine run label after baseline workflow execution")
            run_dir = cli_impl._resolve_gate_c_run_dir(cwd, run_label, target_mode=target_mode)
        else:
            run_dir = (cwd / "artifacts").resolve()

        run_metadata_path = run_dir / "run_metadata.json"
        if not run_metadata_path.exists():
            raise FileNotFoundError(f"run metadata not found: {run_metadata_path}")

        run_metadata = cli_impl._load_config(run_metadata_path)
        run_id = str(run_metadata.get("run_id", "")).strip()
        top_csv = cli_impl._resolve_top10_csv_path(run_dir, run_id=run_id)
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
        "generated_utc": cli_impl._utc_now_iso(),
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
    out_json.write_text(cli_impl.json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
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

