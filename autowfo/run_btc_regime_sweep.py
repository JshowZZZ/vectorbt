import datetime as dt
import os
import shutil
import time
from pathlib import Path

import pandas as pd

from autowfo import data as autowfo_data
from autowfo import artifacts as autowfo_artifacts
from autowfo import evaluator as autowfo_evaluator
from autowfo import metrics as autowfo_metrics
from autowfo import parallel as autowfo_parallel
from autowfo import portfolio as autowfo_portfolio
from autowfo import ranking as autowfo_ranking
from autowfo import registry as autowfo_registry
from autowfo import report as autowfo_report
from autowfo import search as autowfo_search
from autowfo import split as autowfo_split
from autowfo import strategy as autowfo_strategy
from autowfo import engine_helpers
from autowfo import engine_runtime
from autowfo import engine_search
from autowfo import engine_finalize
from autowfo.run_workspace import build_run_workspace

from autowfo.constants import (
    FILTER_NAME_MAP,
    INDICATOR_META,
    INDICATOR_PARAM_FIELDS,
    LABELS,
    REGIME_NAME_MAP,
    REGIME_TYPE_MAP,
)


ARTIFACT_ROW_METADATA_FIELDS = list(autowfo_artifacts.ROW_METADATA_FIELDS)
SWEEP_SCHEMA_FIELDS = engine_helpers._build_sweep_schema_fields(
    artifact_row_metadata_fields=ARTIFACT_ROW_METADATA_FIELDS,
)
COMBO_KEY_FIELDS = SWEEP_SCHEMA_FIELDS["combo_key_fields"]
COMBO_RESULT_FIELDS = SWEEP_SCHEMA_FIELDS["combo_result_fields"]
SYMBOL_RESULT_FIELDS = SWEEP_SCHEMA_FIELDS["symbol_result_fields"]
OOS_SYMBOL_RESULT_FIELDS = SWEEP_SCHEMA_FIELDS["oos_symbol_result_fields"]
STRICT_CONFIG_FIELDS = SWEEP_SCHEMA_FIELDS["strict_config_fields"]


RISK_GRID_LIMITS = {
    "tp_stops": (0.000001, 0.2),
    "sl_stops": (0.000001, 0.2),
    "max_holds": (1, 240),
}

ATR_RISK_GRID_LIMITS = {
    "tp_atr_multipliers": (0.05, 20.0),
    "sl_atr_multipliers": (0.05, 20.0),
}


def _select_indicator_param_options(indicator_param_options, indicator_keys, *, fixed_params):
    filtered_options = {
        key: list(indicator_param_options.get(key, [{}]))
        for key in indicator_keys
    }
    indicator_defaults = autowfo_strategy._indicator_defaults(filtered_options)
    if not fixed_params:
        return filtered_options, indicator_defaults
    fixed_options = {}
    for key in indicator_keys:
        fixed_options[key] = [dict(indicator_defaults.get(key, {}))]
    return fixed_options, indicator_defaults


def _resolve_risk_grid_from_config(config):
    cfg = config if isinstance(config, dict) else {}
    risk_mode = engine_helpers._normalize_risk_mode(cfg.get("risk_mode", "fixed_pct"))

    def _coerce_grid(raw, default_values, cast_fn, min_value=None, max_value=None):
        if raw in (None, ""):
            return list(default_values)
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        parsed = []
        for item in values:
            try:
                value = cast_fn(item)
            except Exception:
                continue
            if min_value is not None and value < min_value:
                continue
            if max_value is not None and value > max_value:
                continue
            parsed.append(value)
        if not parsed:
            return list(default_values)
        unique = []
        for value in parsed:
            if value in unique:
                continue
            unique.append(value)
        return unique

    if risk_mode == "atr_multiple":
        return {
            "risk_mode": risk_mode,
            "tp_stops": _coerce_grid(
                cfg.get("tp_atr_multipliers"),
                [1.5],
                float,
                min_value=ATR_RISK_GRID_LIMITS["tp_atr_multipliers"][0],
                max_value=ATR_RISK_GRID_LIMITS["tp_atr_multipliers"][1],
            ),
            "sl_stops": _coerce_grid(
                cfg.get("sl_atr_multipliers"),
                [1.0],
                float,
                min_value=ATR_RISK_GRID_LIMITS["sl_atr_multipliers"][0],
                max_value=ATR_RISK_GRID_LIMITS["sl_atr_multipliers"][1],
            ),
            "max_holds": _coerce_grid(
                cfg.get("max_holds"),
                [2, 4],
                int,
                min_value=RISK_GRID_LIMITS["max_holds"][0],
                max_value=RISK_GRID_LIMITS["max_holds"][1],
            ),
        }

    return {
        "risk_mode": risk_mode,
        "tp_stops": _coerce_grid(
            cfg.get("tp_stops"),
            [0.003, 0.005],
            float,
            min_value=RISK_GRID_LIMITS["tp_stops"][0],
            max_value=RISK_GRID_LIMITS["tp_stops"][1],
        ),
        "sl_stops": _coerce_grid(
            cfg.get("sl_stops"),
            [0.006, 0.01],
            float,
            min_value=RISK_GRID_LIMITS["sl_stops"][0],
            max_value=RISK_GRID_LIMITS["sl_stops"][1],
        ),
        "max_holds": _coerce_grid(
            cfg.get("max_holds"),
            [2, 4],
            int,
            min_value=RISK_GRID_LIMITS["max_holds"][0],
            max_value=RISK_GRID_LIMITS["max_holds"][1],
        ),
    }


def main():
    base_symbol = "BTC/USDT"
    exchange = "binance"
    fallback_trade_symbols = [
        "ETH/BTC",
        "BNB/BTC",
        "ADA/BTC",
        "XRP/BTC",
        "SOL/BTC",
        "DOGE/BTC",
        "DOT/BTC",
        "LINK/BTC",
        "LTC/BTC",
        "AVAX/BTC",
    ]
    default_trade_symbols = autowfo_data._fetch_top_trade_symbols(
        exchange, limit=10, fallback=fallback_trade_symbols
    )
    artifacts_root = "artifacts"
    os.makedirs(artifacts_root, exist_ok=True)
    runtime_config_override = os.getenv("VBT_RUNTIME_CONFIG_PATH")

    default_config = engine_helpers._load_runtime_config(
        artifacts_root,
        env_mode=os.getenv("VBT_SWEEP_MODE"),
        config_path=runtime_config_override,
    )
    runtime_settings = engine_helpers._resolve_runtime_settings(
        default_config=default_config,
        base_symbol=base_symbol,
        default_trade_symbols=default_trade_symbols,
        available_indicator_keys=list(INDICATOR_META.keys()),
        normalize_split_mode_fn=autowfo_split._normalize_split_mode,
        resolve_ranking_config_fn=autowfo_ranking._resolve_ranking_config,
    )
    search_mode = runtime_settings["search_mode"]
    config_sha256 = autowfo_artifacts._compute_config_sha256(default_config)
    config_path = runtime_config_override or os.path.join(artifacts_root, "sweep_config.json")
    timeframe_configs = runtime_settings["timeframe_configs"]
    combo_sizes = runtime_settings["combo_sizes"]
    combo_seed = runtime_settings["combo_seed"]
    max_workers = runtime_settings["max_workers"]
    combo_segment_start = runtime_settings["combo_segment_start"]
    combo_segment_size = runtime_settings["combo_segment_size"]
    combo_group_fields = runtime_settings["combo_group_fields"]
    trade_symbols = runtime_settings["trade_symbols"]
    indicator_keys = runtime_settings["indicator_subset"]
    strategy_mode = runtime_settings["strategy_mode"]
    state_indicator_sets = runtime_settings["state_indicator_sets"]
    trigger_indicator_sets = runtime_settings["trigger_indicator_sets"]
    allow_shared_indicator_roles = runtime_settings["allow_shared_indicator_roles"]
    state_exit_policy = runtime_settings["state_exit_policy"]
    regime_preset = runtime_settings["regime_preset"]
    regime_name_filter = runtime_settings["regime_name_filter"]
    filter_variants = runtime_settings["filter_variants"]
    enable_htf_trend_gate = runtime_settings["enable_htf_trend_gate"]
    htf_trend_timeframes = runtime_settings["htf_trend_timeframes"]
    htf_trend_windows = runtime_settings["htf_trend_windows"]
    funding_gate_long_thresholds = runtime_settings["funding_gate_long_thresholds"]
    funding_gate_short_thresholds = runtime_settings["funding_gate_short_thresholds"]
    open_interest_provider = runtime_settings["open_interest_provider"]
    pilot_fixed_indicator_params = runtime_settings["pilot_fixed_indicator_params"]
    pilot_single_trend_mom = runtime_settings["pilot_single_trend_mom"]
    wf_train_days = runtime_settings["wf_train_days"]
    wf_test_days = runtime_settings["wf_test_days"]
    wf_step_days = runtime_settings["wf_step_days"]
    wf_valid_days = runtime_settings.get("wf_valid_days", 0)
    wf_mode = runtime_settings["wf_mode"]

    vol_lookbacks = [24]
    vol_zs = [0.8]
    mom_lookbacks = [6, 12]
    trade_mom_lookbacks = [3]
    risk_grid = _resolve_risk_grid_from_config(default_config)
    risk_mode = risk_grid["risk_mode"]
    tp_stops = risk_grid["tp_stops"]
    sl_stops = risk_grid["sl_stops"]
    max_holds = risk_grid["max_holds"]
    if pilot_single_trend_mom and mom_lookbacks:
        mom_lookbacks = [mom_lookbacks[0]]

    rsi_window = 14
    rsi_revert_pairs = [(30, 70), (35, 65), (40, 60)]
    bb_window = 20
    bb_alpha = 2
    atr_window = 14
    base_ma_pairs = [(10, 30), (20, 50)]
    ma_pairs = engine_helpers._build_ma_pairs(base_ma_pairs)
    lookback_refine_step = 4
    obv_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    oi_selected_keys = set(indicator_keys)
    for combo in list(state_indicator_sets or []) + list(trigger_indicator_sets or []):
        oi_selected_keys.update(combo)
    oi_lookbacks = []
    if "oi_roc" in oi_selected_keys:
        oi_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    volume_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    roc_lookbacks = autowfo_strategy._expand_lookback_list([6, 12], lookback_refine_step)
    cmf_lookbacks = autowfo_strategy._expand_lookback_list([20, 30], lookback_refine_step)
    mfi_window = 14
    vroc_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    ad_lookbacks = autowfo_strategy._expand_lookback_list([20, 40], lookback_refine_step)
    cci_lookbacks = autowfo_strategy._expand_lookback_list([14, 20], lookback_refine_step)
    willr_lookbacks = autowfo_strategy._expand_lookback_list([14, 21], lookback_refine_step)
    adx_lookbacks = autowfo_strategy._expand_lookback_list([14, 20], lookback_refine_step)
    trix_lookbacks = autowfo_strategy._expand_lookback_list([12, 18], lookback_refine_step)
    dpo_lookbacks = autowfo_strategy._expand_lookback_list([14, 20], lookback_refine_step)
    efi_lookbacks = autowfo_strategy._expand_lookback_list([13, 26], lookback_refine_step)
    vwma_lookbacks = autowfo_strategy._expand_lookback_list([20, 40], lookback_refine_step)
    ultosc_periods = (7, 14, 28)
    keltner_lookbacks = autowfo_strategy._expand_lookback_list([14, 20], lookback_refine_step)
    donchian_lookbacks = autowfo_strategy._expand_lookback_list([14, 20], lookback_refine_step)
    ppo_fast = 12
    ppo_slow = 26
    ppo_signal = 9
    chop_lookbacks = autowfo_strategy._expand_lookback_list([14, 20], lookback_refine_step)

    fees = 0.001
    slippage_bps = runtime_settings["slippage_bps"]
    spread_bps = runtime_settings["spread_bps"]
    funding_rate_daily = runtime_settings["funding_rate_daily"]
    risk_mode = runtime_settings["risk_mode"]
    capital_mode = runtime_settings["capital_mode"]
    init_cash_usdt = runtime_settings["init_cash_usdt"]
    order_size_pct = runtime_settings["order_size_pct"]
    max_concurrent_positions = runtime_settings["max_concurrent_positions"]
    cache_dir = os.path.join(artifacts_root, "cache_ccxt")
    cache_format = "parquet" if autowfo_data._has_parquet_engine() else "csv"
    run_id = os.getenv("VBT_RUN_ID") or dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    timestamp_utc = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    workspace = build_run_workspace(Path.cwd(), run_id)
    workspace.ensure_directories()
    # Quality filters can be tuned via sweep_config.json.
    min_avg_daily_trades_target = runtime_settings["min_avg_daily_trades_target"]
    min_oos_trades_target = runtime_settings["min_oos_trades_target"]
    top_n_fine = runtime_settings["top_n_fine"]
    ranking_config = runtime_settings["ranking_config"]
    pruning_config = runtime_settings.get("pruning_config")
    history_rows = 20
    leaderboard_path = str(workspace.leaderboard_path)
    registry_path = str(workspace.registry_path)
    status_json_path = str(workspace.status_json_path)
    status_html_path = str(workspace.status_html_path)
    run_metadata_path = str(workspace.run_metadata_path)
    run_metadata_path_run = str(workspace.run_metadata_run_path)
    db_path = str(workspace.db_path)
    control_path = str(workspace.control_path)
    engine_helpers._ensure_control_file(control_path)
    if runtime_config_override and os.path.exists(runtime_config_override):
        config_path = os.path.relpath(Path(runtime_config_override), Path.cwd())
    elif os.path.exists(config_path):
        shutil.copy2(config_path, workspace.runtime_config_path)
        config_path = os.path.relpath(workspace.runtime_config_path, Path.cwd())

    combo_path = str(workspace.combo_summary_path)
    per_symbol_path = str(workspace.symbol_summary_path)
    oos_symbol_path = str(workspace.oos_symbol_summary_path)
    existing_combo_df = pd.read_csv(combo_path, low_memory=False) if os.path.exists(combo_path) else pd.DataFrame()
    existing_symbol_df = pd.read_csv(per_symbol_path, low_memory=False) if os.path.exists(per_symbol_path) else pd.DataFrame()
    autowfo_artifacts._ensure_csv_schema(combo_path, COMBO_RESULT_FIELDS)
    autowfo_artifacts._ensure_csv_schema(per_symbol_path, SYMBOL_RESULT_FIELDS)
    autowfo_artifacts._ensure_csv_schema(oos_symbol_path, OOS_SYMBOL_RESULT_FIELDS)
    autowfo_artifacts._ensure_db_schema(
        db_path,
        "combo_summary",
        COMBO_RESULT_FIELDS,
        indexes=[("idx_combo_timeframe", ["timeframe"])],
    )
    autowfo_artifacts._ensure_db_schema(
        db_path,
        "symbol_summary",
        SYMBOL_RESULT_FIELDS,
        indexes=[
            ("idx_symbol_timeframe", ["timeframe"]),
            ("idx_symbol_symbol", ["symbol"]),
        ],
    )
    autowfo_artifacts._ensure_db_schema(
        db_path,
        "symbol_oos_summary",
        OOS_SYMBOL_RESULT_FIELDS,
        indexes=[
            ("idx_oos_symbol_timeframe", ["timeframe"]),
            ("idx_oos_symbol_symbol", ["symbol"]),
        ],
    )
    if os.path.exists(combo_path):
        existing_combo_df = pd.read_csv(combo_path, low_memory=False)
    if os.path.exists(per_symbol_path):
        existing_symbol_df = pd.read_csv(per_symbol_path, low_memory=False)
    existing_combo_df, existing_symbol_df = engine_helpers._normalize_existing_results(
        existing_combo_df,
        existing_symbol_df,
        COMBO_KEY_FIELDS,
    )
    if strategy_mode == "state_trigger_entry":
        if search_mode != "combo":
            raise ValueError("state_trigger_entry currently supports combo search only")
        if not state_indicator_sets or not trigger_indicator_sets:
            raise ValueError(
                "state_trigger_entry requires non-empty state_indicator_sets and trigger_indicator_sets"
            )
        state_trigger_indicator_keys = list(
            dict.fromkeys(
                [
                    key
                    for combo in list(state_indicator_sets) + list(trigger_indicator_sets)
                    for key in combo
                ]
            )
        )
        indicator_param_options, indicator_defaults = _select_indicator_param_options(
            autowfo_strategy._build_indicator_param_options_coarse(),
            state_trigger_indicator_keys,
            fixed_params=pilot_fixed_indicator_params,
        )
        combo_keys_all = engine_helpers._build_state_trigger_combo_keys(
            state_indicator_sets=state_indicator_sets,
            trigger_indicator_sets=trigger_indicator_sets,
            allow_shared_indicator_roles=allow_shared_indicator_roles,
            combo_seed=combo_seed,
            combo_segment_start=combo_segment_start,
            combo_segment_size=combo_segment_size,
        )
    else:
        indicator_param_options, indicator_defaults = _select_indicator_param_options(
            autowfo_strategy._build_indicator_param_options_coarse(),
            indicator_keys,
            fixed_params=pilot_fixed_indicator_params,
        )
        combo_keys_all = engine_helpers._build_combo_keys(
            indicator_keys=indicator_keys,
            combo_sizes=combo_sizes,
            combo_seed=combo_seed,
            combo_segment_start=combo_segment_start,
            combo_segment_size=combo_segment_size,
        )

    regime_variants = engine_helpers._build_regime_variants(
        rsi_revert_pairs,
        preset=regime_preset,
        regime_name_filter=regime_name_filter,
    )
    if not regime_variants:
        raise ValueError("regime_name_filter removed all regime variants")

    # scanning logic (multi-timeframe, incremental, two-space)
    regime_lookup = {regime["regime_name"]: regime for regime in regime_variants}
    timeframe_days_map = {cfg["timeframe"]: cfg["days"] for cfg in timeframe_configs}

    count_coarse_combos = lambda: engine_helpers._count_coarse_combos(
        regime_variants=regime_variants,
        filter_variants=filter_variants,
        indicator_param_options=indicator_param_options,
        combo_keys_all=combo_keys_all,
        mom_lookbacks=mom_lookbacks,
        vol_lookbacks=vol_lookbacks,
        vol_zs=vol_zs,
        trade_mom_lookbacks=trade_mom_lookbacks,
        tp_stops=tp_stops,
        sl_stops=sl_stops,
        max_holds=max_holds,
    )

    total_combos = count_coarse_combos() * len(timeframe_configs) if search_mode == "combo" else 0
    pending_combo_rows = []
    pending_symbol_rows = []
    pending_oos_symbol_rows = []
    # AWF-108(c): checkpoint / progress frequency configurable via sweep_config.json
    _checkpoint_every_n = max(int(default_config.get("checkpoint_every_n", 200) or 200), 1)
    _progress_every_n = max(int(default_config.get("progress_every_n", 25) or 25), 1)

    lifecycle = engine_helpers._build_run_lifecycle_callbacks(
        total_combos=total_combos,
        run_id=run_id,
        status_json_path=status_json_path,
        status_html_path=status_html_path,
        labels=LABELS,
        control_path=control_path,
        combo_path=combo_path,
        per_symbol_path=per_symbol_path,
        oos_symbol_path=oos_symbol_path,
        db_path=db_path,
        combo_result_fields=COMBO_RESULT_FIELDS,
        symbol_result_fields=SYMBOL_RESULT_FIELDS,
        oos_symbol_result_fields=OOS_SYMBOL_RESULT_FIELDS,
        pending_combo_rows=pending_combo_rows,
        pending_symbol_rows=pending_symbol_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
        format_duration_fn=autowfo_report._format_duration,
        write_status_fn=autowfo_artifacts._write_status,
        append_rows_fn=autowfo_artifacts._append_rows,
        append_db_rows_fn=autowfo_artifacts._append_db_rows,
        normalize_key_value_fn=autowfo_search._normalize_key_value,
        now_fn=time.time,
        sleep_fn=time.sleep,
        build_updated_timestamp_fn=(
            lambda: dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        ),
        checkpoint_every=_checkpoint_every_n,
        progress_every=_progress_every_n,
    )
    emit_progress = lifecycle["emit_progress_fn"]
    _advance_progress_counts = lifecycle["advance_progress_counts_fn"]
    _wait_if_paused = lifecycle["wait_if_paused_fn"]
    _checkpoint = lifecycle["checkpoint_fn"]
    _get_done = lifecycle["get_done_fn"]
    _get_total_combos = lifecycle["get_total_combos_fn"]
    _set_total_combos = lifecycle["set_total_combos_fn"]

    emit_progress(stage="running", force=True)
    sweep_adapters = engine_helpers._build_sweep_adapter_functions(
        combo_key_fields=COMBO_KEY_FIELDS,
        strict_config_fields=STRICT_CONFIG_FIELDS,
        indicator_meta=INDICATOR_META,
        filter_name_map=FILTER_NAME_MAP,
        regime_name_map=REGIME_NAME_MAP,
        regime_type_map=REGIME_TYPE_MAP,
        combo_key_from_dict_impl_fn=autowfo_search._combo_key_from_dict,
        indicator_combo_label_impl_fn=autowfo_report._indicator_combo_label,
        format_indicator_list_impl_fn=autowfo_report._format_indicator_list,
        df_to_html_impl_fn=autowfo_report._df_to_html,
    )
    combo_key_from_dict_fn = sweep_adapters["combo_key_from_dict_fn"]
    indicator_combo_label_fn = sweep_adapters["indicator_combo_label_fn"]
    df_to_html_fn = sweep_adapters["df_to_html_fn"]
    has_all_config_fields_fn = sweep_adapters["has_all_config_fields_fn"]

    _seen_keys_result = engine_helpers._build_seen_keys(
        existing_combo_df,
        has_all_config_fields_fn=has_all_config_fields_fn,
        combo_key_from_dict_fn=combo_key_from_dict_fn,
        # AWF-106d: pass current runtime capital_mode so that CSV rows written
        # before capital_mode was persisted still produce matching seen keys.
        null_fill_overrides={
            "capital_mode": capital_mode,
            "strategy_mode": "combo_entry",
        },
    )
    # Use stripped seen_keys (without data_start/data_end) for cross-run skip
    # decisions so that routine OHLCV refresh (data_end advances each run)
    # does not invalidate all seen_keys and force a full re-evaluation.
    seen_keys = _seen_keys_result["stripped"]

    apply_quality_filters = lambda df: engine_helpers._apply_quality_filters(
        df,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        min_oos_trades_target=min_oos_trades_target,
    )

    shared_pipeline_runtime_context = engine_search._build_shared_pipeline_runtime_context(
        base_symbol=base_symbol,
        trade_symbols=trade_symbols,
        exchange=exchange,
        cache_dir=cache_dir,
        cache_format=cache_format,
        vol_lookbacks=vol_lookbacks,
        vol_zs=vol_zs,
        mom_lookbacks=mom_lookbacks,
        trade_mom_lookbacks=trade_mom_lookbacks,
        rsi_window=rsi_window,
        bb_window=bb_window,
        bb_alpha=bb_alpha,
        atr_window=atr_window,
        ma_pairs=ma_pairs,
        obv_lookbacks=obv_lookbacks,
        oi_lookbacks=oi_lookbacks,
        open_interest_provider=open_interest_provider,
        volume_lookbacks=volume_lookbacks,
        roc_lookbacks=roc_lookbacks,
        cmf_lookbacks=cmf_lookbacks,
        mfi_window=mfi_window,
        vroc_lookbacks=vroc_lookbacks,
        ad_lookbacks=ad_lookbacks,
        cci_lookbacks=cci_lookbacks,
        willr_lookbacks=willr_lookbacks,
        adx_lookbacks=adx_lookbacks,
        trix_lookbacks=trix_lookbacks,
        dpo_lookbacks=dpo_lookbacks,
        efi_lookbacks=efi_lookbacks,
        vwma_lookbacks=vwma_lookbacks,
        ultosc_periods=ultosc_periods,
        keltner_lookbacks=keltner_lookbacks,
        donchian_lookbacks=donchian_lookbacks,
        ppo_fast=ppo_fast,
        ppo_slow=ppo_slow,
        ppo_signal=ppo_signal,
        chop_lookbacks=chop_lookbacks,
        init_cash_usdt=init_cash_usdt,
        capital_mode=capital_mode,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        wf_step_days=wf_step_days,
        wf_valid_days=wf_valid_days,
        wf_mode=wf_mode,
        strategy_mode=strategy_mode,
        state_exit_policy=state_exit_policy,
        indicator_param_fields=INDICATOR_PARAM_FIELDS,
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        filter_variants=filter_variants,
        htf_trend_timeframes=htf_trend_timeframes if enable_htf_trend_gate else [],
        htf_trend_windows=htf_trend_windows if enable_htf_trend_gate else [],
        funding_gate_long_thresholds=funding_gate_long_thresholds,
        funding_gate_short_thresholds=funding_gate_short_thresholds,
        risk_mode=risk_mode,
        order_size_pct=order_size_pct,
        max_concurrent_positions=max_concurrent_positions,
        config_sha256=config_sha256,
        combo_seed=combo_seed,
    )
    prepare_timeframe_runtime_context = engine_search._build_prepare_timeframe_runtime_context_from_shared(
        shared_pipeline_runtime_context=shared_pipeline_runtime_context,
        prepare_timeframe_context_fn=autowfo_data._prepare_timeframe_context,
        build_walk_forward_windows_fn=autowfo_split._build_walk_forward_windows,
        compute_data_fingerprint_fn=autowfo_artifacts._compute_data_fingerprint,
    )
    timeframe_ready_search_context = engine_search._build_timeframe_ready_search_context_from_shared(
        shared_pipeline_runtime_context=shared_pipeline_runtime_context,
        search_mode=search_mode,
        max_workers=max_workers,
        regime_variants=regime_variants,
        regime_lookup=regime_lookup,
        tp_stops=tp_stops,
        sl_stops=sl_stops,
        max_holds=max_holds,
        strategy_mode=strategy_mode,
        state_exit_policy=state_exit_policy,
        combo_keys_all=combo_keys_all,
        indicator_param_options=indicator_param_options,
        existing_combo_df=existing_combo_df,
        combo_group_fields=combo_group_fields,
        top_n_fine=top_n_fine,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        indicator_defaults=indicator_defaults,
        ranking_config=ranking_config,
        seen_keys=seen_keys,
        pending_symbol_rows=pending_symbol_rows,
        pending_combo_rows=pending_combo_rows,
        pending_oos_symbol_rows=pending_oos_symbol_rows,
        combo_key_from_dict_fn=combo_key_from_dict_fn,
        indicator_combo_label_fn=indicator_combo_label_fn,
        iter_indicator_param_combos_fn=autowfo_strategy._iter_indicator_param_combos,
        run_combo_tasks_fn=autowfo_parallel._run_combo_tasks,
        evaluate_combo_task_fn=autowfo_evaluator.evaluate_combo_task,
        wait_if_paused_fn=_wait_if_paused,
        emit_progress_fn=emit_progress,
        checkpoint_fn=_checkpoint,
        on_progress_tick_fn=_advance_progress_counts,
        apply_quality_filters_fn=apply_quality_filters,
        sort_by_score_impl_fn=autowfo_ranking._sort_by_score,
        expand_float_fn=autowfo_strategy._expand_float,
        safe_float_fn=engine_helpers._safe_float,
        refine_indicator_params_fn=autowfo_strategy._refine_indicator_params,
        safe_int_fn=engine_helpers._safe_int,
        pruning_config=pruning_config,
    )
    workspace_paths = {
        **workspace.as_dict(),
        "report_paths": None,
    }
    finalize_pipeline_context = engine_finalize._build_finalize_pipeline_context_from_shared(
        shared_pipeline_runtime_context=shared_pipeline_runtime_context,
        combo_path=combo_path,
        per_symbol_path=per_symbol_path,
        out_dir=str(workspace.results_dir),
        run_id=run_id,
        timeframe_configs=timeframe_configs,
        timeframe_days_map=timeframe_days_map,
        safe_int_fn=engine_helpers._safe_int,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        apply_quality_filters_fn=apply_quality_filters,
        top_by_score_impl_fn=autowfo_ranking._top_by_score,
        ranking_config=ranking_config,
        history_rows=history_rows,
        labels=LABELS,
        timestamp_utc=timestamp_utc,
        leaderboard_path=leaderboard_path,
        run_metadata_path=run_metadata_path,
        run_metadata_path_run=run_metadata_path_run,
        registry_path=registry_path,
        workspace_paths=workspace_paths,
        search_mode=search_mode,
        config_path=config_path,
        prepare_timeframe_context_fn=autowfo_data._prepare_timeframe_context,
        indicator_combo_label_fn=indicator_combo_label_fn,
        coerce_indicator_params_fn=autowfo_strategy._coerce_indicator_params,
        pick_series_from_map_fn=autowfo_strategy._pick_series_from_map,
        apply_indicator_combo_fn=autowfo_strategy._apply_indicator_combo,
        timeframe_to_hours_fn=autowfo_metrics._timeframe_to_hours,
        run_pf_fn=autowfo_portfolio._run_pf,
        plot_portfolio_fn=autowfo_report._plot_portfolio,
        calc_pf_series_fn=autowfo_metrics._calc_pf_series,
        build_walk_forward_slices_fn=autowfo_split._build_walk_forward_slices,
        df_to_html_fn=df_to_html_fn,
        combine_data_fingerprints_fn=autowfo_artifacts._combine_data_fingerprints,
        write_run_metadata_fn=autowfo_artifacts._write_run_metadata,
        update_run_registry_fn=autowfo_registry._update_run_registry,
    )

    finalize_result = engine_search._run_timeframe_pipeline(
        timeframe_configs=timeframe_configs,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        search_mode=search_mode,
        count_coarse_combos_fn=count_coarse_combos,
        emit_progress_fn=emit_progress,
        get_done_fn=_get_done,
        get_total_combos_fn=_get_total_combos,
        set_total_combos_fn=_set_total_combos,
        prepare_timeframe_runtime_context=prepare_timeframe_runtime_context,
        prepare_timeframe_runtime_fn=engine_runtime._prepare_timeframe_runtime,
        timeframe_ready_search_context=timeframe_ready_search_context,
        run_timeframe_ready_search_fn=engine_search._run_timeframe_ready_search,
        run_timeframe_ready_search_with_refine_tracking_fn=(
            engine_search._run_timeframe_ready_search_with_refine_tracking
        ),
        timeframe_to_hours_fn=autowfo_metrics._timeframe_to_hours,
        finalize_pipeline_context=finalize_pipeline_context,
        checkpoint_fn=_checkpoint,
        run_finalize_pipeline_fn=engine_finalize._run_finalize_pipeline,
    )
    if not engine_search._handle_finalize_result(
        finalize_result=finalize_result,
        emit_progress_fn=emit_progress,
    ):
        return


if __name__ == "__main__":
    main()

