"""Compatibility facade for split command helpers (AWF-157)."""

from __future__ import annotations

from .core_batch import (
    _compute_job_key,
    _load_batch_state,
    _parse_batch_jobs,
    _preflight_batch_jobs,
    _run_batch_job_single,
    _run_batch_jobs_parallel,
    _write_batch_state,
)
from .core_patrol import (
    _append_patrol_log,
    _build_cron_notification_text,
    _build_freshness_alert,
    _build_top_change_lines,
    _default_cron_notify_state,
    _dispatch_cron_notifications,
    _extract_top_entities,
    _format_freshness_line,
    _parse_datetime_utc,
    _post_json,
    _read_cron_notify_state,
    _run_patrol_cycle,
    _safe_float,
    _trim_text,
    _write_cron_notify_state,
)
from .core_utils import (
    _build_timeframe_days_map,
    _compute_coverage_gaps,
    _extract_registry_untested_pairs,
    _json_sha256,
    _load_config,
    _resolve_path,
    _slug_text,
    _split_csv_fields,
    _utc_now_iso,
)
from .core_workflow import (
    _latest_run_label,
    _list_run_labels,
    _resolve_gate_c_run_dir,
    _resolve_gate_c_target_mode,
    _resolve_top10_csv_path,
    _run_module,
    _run_workflow,
    _write_runtime_config,
)

__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]

