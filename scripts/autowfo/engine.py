"""Engine/orchestration helpers extracted from run_btc_regime_sweep monolith.

This module re-exports all public engine symbols from sub-modules for backward
compatibility.  Consumers continue to ``from .engine import X`` or
``from scripts.autowfo.engine import X`` without changes.

Sub-modules (AWF-018 decomposition):
    engine_helpers   -- config, schema, utility, progress/lifecycle
    engine_runtime   -- timeframe prep, combo task/row building, regime signals
    engine_report    -- HTML generation, best replay, leaderboard rendering
    engine_search    -- plan iteration, search execution, pipeline orchestration
    engine_finalize  -- result loading, finalize pipeline, metadata persistence
"""

# ---------------------------------------------------------------------------
# engine_helpers  (config, schema, utility, progress/lifecycle)
# ---------------------------------------------------------------------------
from .engine_helpers import (  # noqa: F401
    DEFAULT_CONFIG,
    _apply_quality_filters,
    _build_combo_keys,
    _build_ma_pairs,
    _build_progress_payload,
    _build_regime_variants,
    _build_run_lifecycle_callbacks,
    _build_seen_keys,
    _strip_data_range_from_combo_key,
    _build_sweep_adapter_functions,
    _build_sweep_schema_fields,
    _checkpoint_pending_rows,
    _count_coarse_combos,
    _ensure_control_file,
    _fallback_activity_filter,
    _has_all_config_fields,
    _load_runtime_config,
    _normalize_existing_results,
    _normalize_search_mode,
    _normalize_trade_symbols,
    _read_control,
    _resolve_runtime_settings,
    _safe_float,
    _safe_int,
    _safe_positive_config_int,
    _should_checkpoint,
    _should_emit_progress,
)

# ---------------------------------------------------------------------------
# engine_runtime  (timeframe prep, combo task/row building, regime signals)
# ---------------------------------------------------------------------------
from .engine_runtime import (  # noqa: F401
    _append_eval_result_rows,
    _build_combo_key_values,
    _build_combo_row,
    _build_combo_task_payload,
    _build_symbol_row,
    _build_trade_mom_filters,
    _compute_effective_costs,
    _prepare_timeframe_runtime,
    _resolve_regime_signals,
)

# ---------------------------------------------------------------------------
# engine_report  (HTML generation, best replay, leaderboard rendering)
# ---------------------------------------------------------------------------
from .engine_report import (  # noqa: F401
    _append_leaderboard_row,
    _build_best_report_frames,
    _build_leaderboard_report_html,
    _build_leaderboard_views,
    _build_report_file_paths,
    _build_report_html,
    _build_report_table_html_sections,
    _leaderboard_report_columns,
    _prepare_best_replay_payload,
    _summary_report_columns,
    _top_report_columns,
    _write_report_files,
)

# ---------------------------------------------------------------------------
# engine_search  (plan iteration, search execution, pipeline orchestration)
# ---------------------------------------------------------------------------
from .engine_search import (  # noqa: F401
    _build_prepare_timeframe_runtime_context,
    _build_prepare_timeframe_runtime_context_from_shared,
    _build_prepare_timeframe_runtime_kwargs,
    _build_prepare_timeframe_runtime_kwargs_from_context,
    _build_refine_targets,
    _build_shared_pipeline_runtime_context,
    _build_timeframe_execution_callbacks,
    _build_timeframe_ready_search_context,
    _build_timeframe_ready_search_context_from_shared,
    _build_timeframe_ready_search_kwargs,
    _build_timeframe_ready_search_kwargs_from_context,
    _default_refine_steps,
    _handle_finalize_result,
    _iter_coarse_plan,
    _prepare_timeframe_runtime_or_skip,
    _run_combo_eval_step,
    _run_finalize_after_timeframe_loop,
    _run_parallel_combo_search_for_timeframe,
    _run_search_for_timeframe,
    _run_timeframe_pipeline,
    _run_timeframe_ready_search,
    _run_timeframe_ready_search_with_refine_tracking,
    _run_timeframe_search_and_finalize,
    _run_timeframe_search_loop,
)

# ---------------------------------------------------------------------------
# engine_finalize  (result loading, finalize pipeline, metadata persistence)
# ---------------------------------------------------------------------------
from .engine_finalize import (  # noqa: F401
    _build_completion_output_map,
    _build_finalize_pipeline_context,
    _build_finalize_pipeline_context_from_shared,
    _build_finalize_pipeline_kwargs,
    _build_finalize_pipeline_kwargs_from_context,
    _build_leaderboard_row_payload,
    _build_run_metadata_payload,
    _load_result_frames,
    _persist_run_metadata_and_registry,
    _pick_best_from_top,
    _prepare_best_timeframe_context,
    _run_finalize_pipeline,
    _select_current_combo_df,
    _write_run_snapshot_files,
)
