import datetime as dt
import os
import time

import numpy as np
import pandas as pd

from scripts.autowfo import data as autowfo_data
from scripts.autowfo import artifacts as autowfo_artifacts
from scripts.autowfo import engine as autowfo_engine
from scripts.autowfo import evaluator as autowfo_evaluator
from scripts.autowfo import metrics as autowfo_metrics
from scripts.autowfo import parallel as autowfo_parallel
from scripts.autowfo import portfolio as autowfo_portfolio
from scripts.autowfo import ranking as autowfo_ranking
from scripts.autowfo import report as autowfo_report
from scripts.autowfo import search as autowfo_search
from scripts.autowfo import split as autowfo_split
from scripts.autowfo import strategy as autowfo_strategy

from scripts.autowfo.constants import (
    FILTER_NAME_MAP,
    INDICATOR_META,
    INDICATOR_PARAM_FIELDS,
    LABELS,
    REGIME_NAME_MAP,
    REGIME_TYPE_MAP,
)


ARTIFACT_ROW_METADATA_FIELDS = list(autowfo_artifacts.ROW_METADATA_FIELDS)


COMBO_KEY_FIELDS = [
    "timeframe",
    "data_days",
    "exchange",
    "base_symbol",
    "trade_symbols_key",
    "capital_mode",
    "fees",
    "slippage_bps",
    "spread_bps",
    "funding_rate_daily",
    "order_size_pct",
    "max_concurrent_positions",
    "init_cash_usdt",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "data_start",
    "data_end",
    "regime_name",
    "regime_type",
    "vol_mode",
    "regime_rsi_long",
    "regime_rsi_short",
    "filter_name",
    "indicator_list",
    "indicator_count",
    "vol_lookback",
    "vol_z",
    "mom_lookback",
    "trade_mom_lookback",
    "tp_stop",
    "sl_stop",
    "max_hold",
    "rsi_window",
    "rsi_long",
    "rsi_short",
    "bb_width",
    "atr_ratio",
    "ma_fast",
    "ma_slow",
    "macd_hist_ratio",
    "stoch_long",
    "stoch_short",
    "obv_lookback",
    "volume_lookback",
    "volume_z",
    "roc_lookback",
    "roc_threshold",
    "mfi_long",
    "mfi_short",
    "cmf_lookback",
    "cmf_threshold",
    "vroc_lookback",
    "vroc_threshold",
    "ad_lookback",
]

COMBO_RESULT_FIELDS = COMBO_KEY_FIELDS + ARTIFACT_ROW_METADATA_FIELDS + [
    "avg_total_return_pct",
    "avg_win_rate_pct",
    "avg_avg_trade_pct",
    "avg_max_drawdown_pct",
    "avg_position_coverage_pct",
    "avg_total_trades",
    "min_total_trades",
    "avg_daily_trades",
    "avg_hold_hours",
    "sym_avg_total_return_pct",
    "sym_avg_win_rate_pct",
    "sym_avg_avg_trade_pct",
    "sym_avg_max_drawdown_pct",
    "sym_avg_position_coverage_pct",
    "sym_avg_total_trades",
    "sym_min_total_trades",
    "sym_avg_daily_trades",
    "sym_avg_hold_hours",
    "oos_avg_total_return_pct",
    "oos_avg_win_rate_pct",
    "oos_avg_avg_trade_pct",
    "oos_avg_max_drawdown_pct",
    "oos_avg_position_coverage_pct",
    "oos_avg_total_trades",
    "oos_min_total_trades",
    "oos_avg_daily_trades",
    "oos_avg_hold_hours",
    "oos_segments",
]

SYMBOL_RESULT_FIELDS = [
    "timeframe",
    "data_days",
    "exchange",
    "base_symbol",
    "trade_symbols_key",
    "capital_mode",
    "fees",
    "order_size_pct",
    "max_concurrent_positions",
    "init_cash_usdt",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "data_start",
    "data_end",
    *ARTIFACT_ROW_METADATA_FIELDS,
    "symbol",
    "regime_name",
    "regime_type",
    "vol_mode",
    "regime_rsi_long",
    "regime_rsi_short",
    "filter_name",
    "indicator_list",
    "indicator_count",
    "vol_lookback",
    "vol_z",
    "mom_lookback",
    "trade_mom_lookback",
    "tp_stop",
    "sl_stop",
    "max_hold",
    "rsi_window",
    "rsi_long",
    "rsi_short",
    "bb_width",
    "atr_ratio",
    "ma_fast",
    "ma_slow",
    "macd_hist_ratio",
    "stoch_long",
    "stoch_short",
    "obv_lookback",
    "volume_lookback",
    "volume_z",
    "roc_lookback",
    "roc_threshold",
    "mfi_long",
    "mfi_short",
    "cmf_lookback",
    "cmf_threshold",
    "vroc_lookback",
    "vroc_threshold",
    "ad_lookback",
    "total_return_pct",
    "total_profit",
    "total_trades",
    "win_rate_pct",
    "avg_trade_pct",
    "max_drawdown_pct",
    "position_coverage_pct",
    "avg_hold_hours",
]

STRICT_CONFIG_FIELDS = [
    "exchange",
    "base_symbol",
    "trade_symbols_key",
    "capital_mode",
    "fees",
    "order_size_pct",
    "max_concurrent_positions",
    "init_cash_usdt",
    "wf_train_days",
    "wf_test_days",
    "wf_step_days",
    "data_start",
    "data_end",
]


# --- Convenience helpers (not yet extracted to autowfo) ---

def _combo_key_from_dict(values):
    return autowfo_search._combo_key_from_dict(values, COMBO_KEY_FIELDS)


def _safe_int(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return int(value)


def _safe_float(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return float(value)


def _has_all_config_fields(values):
    for field in STRICT_CONFIG_FIELDS:
        val = values.get(field)
        if val is None:
            return False
        if isinstance(val, float) and np.isnan(val):
            return False
        if isinstance(val, str) and not val:
            return False
    return True


def _indicator_combo_label(combo_keys):
    return autowfo_report._indicator_combo_label(combo_keys, INDICATOR_META)


def _format_indicator_list(value):
    return autowfo_report._format_indicator_list(value, INDICATOR_META)


def _df_to_html(df, columns, label_map):
    return autowfo_report._df_to_html(
        df, columns, label_map,
        FILTER_NAME_MAP, REGIME_NAME_MAP, REGIME_TYPE_MAP,
        format_indicator_list_fn=_format_indicator_list,
    )


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
    out_dir = "artifacts"
    os.makedirs(out_dir, exist_ok=True)

    default_config = autowfo_engine._load_runtime_config(
        out_dir,
        env_mode=os.getenv("VBT_SWEEP_MODE"),
    )
    search_mode = autowfo_engine._normalize_search_mode(default_config.get("search_mode", "combo"))
    config_sha256 = autowfo_artifacts._compute_config_sha256(default_config)
    config_path = os.path.join(out_dir, "sweep_config.json")
    timeframe_configs = default_config["timeframes"]
    combo_sizes = default_config["combo_sizes"]
    combo_seed = int(default_config.get("combo_seed", 42))
    max_workers = max(int(default_config.get("max_workers", 1) or 1), 1)
    combo_segment_start = int(default_config.get("combo_segment_start", 0))
    combo_segment_size = default_config.get("combo_segment_size")
    combo_group_fields = default_config.get("combo_group_fields", ["indicator_list", "regime_name", "vol_mode"])
    trade_symbols = autowfo_engine._normalize_trade_symbols(
        default_config.get("trade_symbols", default_trade_symbols),
        base_symbol=base_symbol,
        default_trade_symbols=default_trade_symbols,
    )

    wf_train_days = autowfo_engine._safe_positive_config_int(default_config, "wf_train_days", 120)
    wf_test_days = autowfo_engine._safe_positive_config_int(default_config, "wf_test_days", 30)
    wf_step_days = autowfo_engine._safe_positive_config_int(default_config, "wf_step_days", 30)

    vol_lookbacks = [24]
    vol_zs = [0.8]
    mom_lookbacks = [6, 12]
    trade_mom_lookbacks = [3]
    tp_stops = [0.003, 0.005]
    sl_stops = [0.006, 0.01]
    max_holds = [2, 4]

    rsi_window = 14
    rsi_revert_pairs = [(30, 70), (35, 65), (40, 60)]
    bb_window = 20
    bb_alpha = 2
    atr_window = 14
    base_ma_pairs = [(10, 30), (20, 50)]
    ma_pairs = autowfo_engine._build_ma_pairs(base_ma_pairs)
    lookback_refine_step = 4
    obv_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    volume_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    roc_lookbacks = autowfo_strategy._expand_lookback_list([6, 12], lookback_refine_step)
    cmf_lookbacks = autowfo_strategy._expand_lookback_list([20, 30], lookback_refine_step)
    mfi_window = 14
    vroc_lookbacks = autowfo_strategy._expand_lookback_list([12, 24], lookback_refine_step)
    ad_lookbacks = autowfo_strategy._expand_lookback_list([20, 40], lookback_refine_step)

    fees = 0.001
    slippage_bps = float(default_config.get("slippage_bps", 0.0) or 0.0)
    spread_bps = float(default_config.get("spread_bps", 0.0) or 0.0)
    funding_rate_daily = float(default_config.get("funding_rate_daily", 0.0) or 0.0)
    capital_mode = str(default_config.get("capital_mode", "shared") or "shared").lower()
    if capital_mode not in {"shared", "per_symbol"}:
        capital_mode = "shared"
    init_cash_usdt = float(default_config.get("init_cash_usdt", 1000) or 1000)
    order_size_pct = float(default_config.get("order_size_pct", 0.5) or 0.5)
    if order_size_pct > 1:
        order_size_pct = order_size_pct / 100.0
    if order_size_pct <= 0:
        order_size_pct = 0.5
    max_concurrent_positions = int(default_config.get("max_concurrent_positions", 2) or 2)
    cache_dir = os.path.join(out_dir, "cache_ccxt")
    cache_format = "parquet" if autowfo_data._has_parquet_engine() else "csv"
    run_id = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    timestamp_utc = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    # Quality filters can be tuned via sweep_config.json.
    min_avg_daily_trades_target = float(default_config.get("min_avg_daily_trades_target", 5.0) or 5.0)
    if min_avg_daily_trades_target < 0:
        min_avg_daily_trades_target = 0.0
    min_oos_trades_target = int(default_config.get("min_oos_trades_target", 1) or 1)
    if min_oos_trades_target < 0:
        min_oos_trades_target = 0
    top_n_fine = int(default_config.get("top_n_refine", 50))
    history_rows = 20
    leaderboard_path = os.path.join(out_dir, "leaderboard.csv")
    status_json_path = os.path.join(out_dir, "run_status.json")
    status_html_path = os.path.join(out_dir, "run_status.html")
    run_metadata_path = os.path.join(out_dir, "run_metadata.json")
    run_metadata_path_run = os.path.join(out_dir, f"run_metadata_{run_id}.json")
    db_path = os.path.join(out_dir, "results.db")
    control_path = os.path.join(out_dir, "run_control.json")
    autowfo_engine._ensure_control_file(control_path)

    combo_path = os.path.join(out_dir, "param_sweep_combo_summary.csv")
    per_symbol_path = os.path.join(out_dir, "param_sweep_symbol_summary.csv")
    existing_combo_df = pd.read_csv(combo_path, low_memory=False) if os.path.exists(combo_path) else pd.DataFrame()
    existing_symbol_df = pd.read_csv(per_symbol_path, low_memory=False) if os.path.exists(per_symbol_path) else pd.DataFrame()
    autowfo_artifacts._ensure_csv_schema(combo_path, COMBO_RESULT_FIELDS)
    autowfo_artifacts._ensure_csv_schema(per_symbol_path, SYMBOL_RESULT_FIELDS)
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
    if os.path.exists(combo_path):
        existing_combo_df = pd.read_csv(combo_path, low_memory=False)
    if os.path.exists(per_symbol_path):
        existing_symbol_df = pd.read_csv(per_symbol_path, low_memory=False)
    existing_combo_df, existing_symbol_df = autowfo_engine._normalize_existing_results(
        existing_combo_df,
        existing_symbol_df,
        COMBO_KEY_FIELDS,
    )
    indicator_param_options = autowfo_strategy._build_indicator_param_options_coarse()
    indicator_defaults = autowfo_strategy._indicator_defaults(indicator_param_options)
    combo_keys_all = autowfo_engine._build_combo_keys(
        indicator_keys=list(INDICATOR_META.keys()),
        combo_sizes=combo_sizes,
        combo_seed=combo_seed,
        combo_segment_start=combo_segment_start,
        combo_segment_size=combo_segment_size,
    )

    regime_variants = autowfo_engine._build_regime_variants(rsi_revert_pairs)

    # scanning logic (multi-timeframe, incremental, two-space)
    regime_lookup = {regime["regime_name"]: regime for regime in regime_variants}
    timeframe_days_map = {cfg["timeframe"]: cfg["days"] for cfg in timeframe_configs}
    timeframe_fingerprints = []

    def count_coarse_combos():
        return autowfo_engine._count_coarse_combos(
            regime_variants=regime_variants,
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
    done = 0
    skipped = 0
    start_ts = time.time()
    last_progress_ts = 0.0
    progress_every = 25
    progress_min_seconds = 5

    def emit_progress(stage="running", force=False):
        nonlocal last_progress_ts, done, skipped, total_combos
        now = time.time()
        if not autowfo_engine._should_emit_progress(
            done=done,
            force=force,
            last_progress_ts=last_progress_ts,
            now=now,
            progress_every=progress_every,
            progress_min_seconds=progress_min_seconds,
        ):
            return
        payload = autowfo_engine._build_progress_payload(
            run_id=run_id,
            stage=stage,
            total=total_combos,
            done=done,
            skipped=skipped,
            elapsed_seconds=now - start_ts,
            updated=dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            format_duration_fn=autowfo_report._format_duration,
        )
        autowfo_artifacts._write_status(status_json_path, status_html_path, payload, LABELS)
        print(
            f"[{stage}] {done}/{total_combos} ({payload['percent']}%) "
            f"skipped {skipped} elapsed {payload['elapsed']} eta {payload['eta']}",
            flush=True,
        )
        last_progress_ts = now

    def _read_control():
        return autowfo_engine._read_control(control_path)

    def _wait_if_paused(stage_label):
        while True:
            control = _read_control()
            if not control.get("paused"):
                return
            emit_progress(stage=f"{stage_label} paused", force=True)
            time.sleep(2)

    def _checkpoint(force=False):
        nonlocal last_checkpoint_ts, last_checkpoint_done
        if not pending_combo_rows and not pending_symbol_rows:
            return
        now = time.time()
        if not autowfo_engine._should_checkpoint(
            done=done,
            force=force,
            last_checkpoint_done=last_checkpoint_done,
            last_checkpoint_ts=last_checkpoint_ts,
            now=now,
            checkpoint_every=checkpoint_every,
            checkpoint_min_seconds=checkpoint_min_seconds,
        ):
            return
        autowfo_artifacts._append_rows(combo_path, pending_combo_rows, COMBO_RESULT_FIELDS)
        autowfo_artifacts._append_rows(per_symbol_path, pending_symbol_rows, SYMBOL_RESULT_FIELDS)
        try:
            autowfo_artifacts._append_db_rows(db_path, "combo_summary", pending_combo_rows, COMBO_RESULT_FIELDS,
                                               normalize_key_value_fn=autowfo_search._normalize_key_value)
            autowfo_artifacts._append_db_rows(db_path, "symbol_summary", pending_symbol_rows, SYMBOL_RESULT_FIELDS,
                                               normalize_key_value_fn=autowfo_search._normalize_key_value)
        except Exception as exc:
            print(f"[warn] db write failed: {exc}")
        pending_combo_rows.clear()
        pending_symbol_rows.clear()
        last_checkpoint_ts = now
        last_checkpoint_done = done

    emit_progress(stage="running", force=True)

    seen_keys = autowfo_engine._build_seen_keys(
        existing_combo_df,
        has_all_config_fields_fn=_has_all_config_fields,
        combo_key_from_dict_fn=_combo_key_from_dict,
    )

    pending_combo_rows = []
    pending_symbol_rows = []
    timeframe_ranges = []
    last_checkpoint_ts = time.time()
    last_checkpoint_done = 0
    checkpoint_every = 200
    checkpoint_min_seconds = 30

    def apply_quality_filters(df):
        return autowfo_engine._apply_quality_filters(
            df,
            min_avg_daily_trades_target=min_avg_daily_trades_target,
            min_oos_trades_target=min_oos_trades_target,
        )

    for tf_cfg in timeframe_configs:
        timeframe = tf_cfg["timeframe"]
        data_days = tf_cfg["days"]
        stage_prefix = f"{timeframe}"
        bar_hours = autowfo_metrics._timeframe_to_hours(timeframe)
        try:
            ctx = autowfo_data._prepare_timeframe_context(
                timeframe=timeframe,
                data_days=data_days,
                base_symbol=base_symbol,
                trade_symbols=trade_symbols,
                exchange=exchange,
                cache_dir=cache_dir,
                cache_format=cache_format,
                vol_lookbacks=vol_lookbacks,
                mom_lookbacks=mom_lookbacks,
                trade_mom_lookbacks=trade_mom_lookbacks,
                rsi_window=rsi_window,
                bb_window=bb_window,
                bb_alpha=bb_alpha,
                atr_window=atr_window,
                ma_pairs=ma_pairs,
                obv_lookbacks=obv_lookbacks,
                volume_lookbacks=volume_lookbacks,
                roc_lookbacks=roc_lookbacks,
                cmf_lookbacks=cmf_lookbacks,
                mfi_window=mfi_window,
                vroc_lookbacks=vroc_lookbacks,
                ad_lookbacks=ad_lookbacks,
                init_cash_usdt=init_cash_usdt,
                capital_mode=capital_mode,
            )
        except Exception as exc:
            if search_mode == "combo":
                total_combos = max(total_combos - count_coarse_combos(), done)
            emit_progress(stage=f"{stage_prefix} skipped", force=True)
            print(f"[warn] timeframe {timeframe} skipped: {exc}")
            continue

        trade_symbols_tf = ctx["trade_symbols"]
        plot_symbol_tf = trade_symbols_tf[0]
        timeframe_ranges.append(f"{timeframe} ({data_days}d): {ctx['data_range']}")
        timeframe_data_fingerprint = autowfo_artifacts._compute_data_fingerprint(
            {
                "exchange": exchange,
                "base_symbol": base_symbol,
                "trade_symbols": trade_symbols_tf,
                "timeframe": timeframe,
                "data_days": data_days,
                "data_start": str(ctx["trade_close"].index[0]),
                "data_end": str(ctx["trade_close"].index[-1]),
            }
        )
        timeframe_fingerprints.append(timeframe_data_fingerprint)
        wf_slices = autowfo_split._build_walk_forward_slices(
            ctx["trade_close"].index, wf_train_days, wf_test_days, wf_step_days
        )
        if not wf_slices:
            required_days = wf_train_days + wf_test_days
            print(
                f"[warn] timeframe {timeframe} has no walk-forward segments: "
                f"available_days={ctx['total_days']} required_days>={required_days}. "
                "OOS metrics will be empty."
            )

        runtime_eval = {
            "ctx": ctx,
            "trade_symbols_tf": trade_symbols_tf,
            "timeframe": timeframe,
            "data_days": data_days,
            "exchange": exchange,
            "base_symbol": base_symbol,
            "capital_mode": capital_mode,
            "fees": fees,
            "slippage_bps": slippage_bps,
            "spread_bps": spread_bps,
            "funding_rate_daily": funding_rate_daily,
            "order_size_pct": order_size_pct,
            "max_concurrent_positions": max_concurrent_positions,
            "init_cash_usdt": init_cash_usdt,
            "wf_train_days": wf_train_days,
            "wf_test_days": wf_test_days,
            "wf_step_days": wf_step_days,
            "rsi_window": rsi_window,
            "bar_hours": bar_hours,
            "wf_slices": wf_slices,
            "config_sha256": config_sha256,
            "data_fingerprint": timeframe_data_fingerprint,
        }

        def _build_combo_task(
            regime,
            indicator_combo,
            combo_params,
            vol_lookback,
            vol_z,
            mom_lookback,
            trade_mom_lookback,
            tp_stop,
            sl_stop,
            max_hold,
        ):
            indicator_combo = tuple(indicator_combo)
            combo_params = dict(combo_params)
            indicator_list = ",".join(indicator_combo)
            filter_name = _indicator_combo_label(indicator_combo)
            param_payload = {field: combo_params.get(field) for field in INDICATOR_PARAM_FIELDS}
            combo_key_values = autowfo_engine._build_combo_key_values(
                timeframe=timeframe,
                data_days=data_days,
                exchange=exchange,
                base_symbol=base_symbol,
                trade_symbols_tf=trade_symbols_tf,
                capital_mode=capital_mode,
                fees=fees,
                slippage_bps=slippage_bps,
                spread_bps=spread_bps,
                funding_rate_daily=funding_rate_daily,
                order_size_pct=order_size_pct,
                max_concurrent_positions=max_concurrent_positions,
                init_cash_usdt=init_cash_usdt,
                wf_train_days=wf_train_days,
                wf_test_days=wf_test_days,
                wf_step_days=wf_step_days,
                data_start=ctx["trade_close"].index[0],
                data_end=ctx["trade_close"].index[-1],
                regime=regime,
                filter_name=filter_name,
                indicator_list=indicator_list,
                indicator_combo=indicator_combo,
                vol_lookback=vol_lookback,
                vol_z=vol_z,
                mom_lookback=mom_lookback,
                trade_mom_lookback=trade_mom_lookback,
                tp_stop=tp_stop,
                sl_stop=sl_stop,
                max_hold=max_hold,
                rsi_window=rsi_window,
                param_payload=param_payload,
            )
            combo_key = _combo_key_from_dict(combo_key_values)
            task_payload = {
                "combo_key": combo_key,
                "regime": regime,
                "indicator_combo": indicator_combo,
                "combo_params": combo_params,
                "filter_name": filter_name,
                "indicator_list": indicator_list,
                "vol_lookback": vol_lookback,
                "vol_z": vol_z,
                "mom_lookback": mom_lookback,
                "trade_mom_lookback": trade_mom_lookback,
                "tp_stop": tp_stop,
                "sl_stop": sl_stop,
                "max_hold": max_hold,
            }
            return combo_key, task_payload

        def _append_eval_result(result, task_meta):
            metrics_values = result.get("metrics_values")
            if not isinstance(metrics_values, dict):
                return

            regime = task_meta["regime"]
            indicator_combo = tuple(task_meta["indicator_combo"])
            filter_name = task_meta["filter_name"]
            indicator_list = task_meta["indicator_list"]
            vol_lookback = task_meta["vol_lookback"]
            vol_z = task_meta["vol_z"]
            mom_lookback = task_meta["mom_lookback"]
            trade_mom_lookback = task_meta["trade_mom_lookback"]
            tp_stop = task_meta["tp_stop"]
            sl_stop = task_meta["sl_stop"]
            max_hold = task_meta["max_hold"]
            metrics = {
                name: pd.Series(values).reindex(trade_symbols_tf)
                for name, values in metrics_values.items()
            }
            variant_params = result["variant_params"]
            regime_rsi_long = result["regime_rsi_long"]
            regime_rsi_short = result["regime_rsi_short"]

            for symbol in trade_symbols_tf:
                pending_symbol_rows.append(
                    autowfo_engine._build_symbol_row(
                        timeframe=timeframe,
                        data_days=data_days,
                        exchange=exchange,
                        base_symbol=base_symbol,
                        trade_symbols_tf=trade_symbols_tf,
                        capital_mode=capital_mode,
                        fees=fees,
                        order_size_pct=order_size_pct,
                        max_concurrent_positions=max_concurrent_positions,
                        init_cash_usdt=init_cash_usdt,
                        wf_train_days=wf_train_days,
                        wf_test_days=wf_test_days,
                        wf_step_days=wf_step_days,
                        data_start=ctx["trade_close"].index[0],
                        data_end=ctx["trade_close"].index[-1],
                        symbol=symbol,
                        regime=regime,
                        regime_rsi_long=regime_rsi_long,
                        regime_rsi_short=regime_rsi_short,
                        filter_name=filter_name,
                        indicator_list=indicator_list,
                        indicator_combo=indicator_combo,
                        vol_lookback=vol_lookback,
                        vol_z=vol_z,
                        mom_lookback=mom_lookback,
                        trade_mom_lookback=trade_mom_lookback,
                        tp_stop=tp_stop,
                        sl_stop=sl_stop,
                        max_hold=max_hold,
                        rsi_window=rsi_window,
                        variant_params=variant_params,
                        metrics=metrics,
                        config_sha256=config_sha256,
                        data_fingerprint=timeframe_data_fingerprint,
                    )
                )

            combo_row = autowfo_engine._build_combo_row(
                timeframe=timeframe,
                data_days=data_days,
                exchange=exchange,
                base_symbol=base_symbol,
                trade_symbols_tf=trade_symbols_tf,
                fees=fees,
                slippage_bps=slippage_bps,
                spread_bps=spread_bps,
                funding_rate_daily=funding_rate_daily,
                order_size_pct=order_size_pct,
                max_concurrent_positions=max_concurrent_positions,
                init_cash_usdt=init_cash_usdt,
                wf_train_days=wf_train_days,
                wf_test_days=wf_test_days,
                wf_step_days=wf_step_days,
                data_start=ctx["trade_close"].index[0],
                data_end=ctx["trade_close"].index[-1],
                regime=regime,
                regime_rsi_long=regime_rsi_long,
                regime_rsi_short=regime_rsi_short,
                filter_name=filter_name,
                indicator_list=indicator_list,
                indicator_combo=indicator_combo,
                vol_lookback=vol_lookback,
                vol_z=vol_z,
                mom_lookback=mom_lookback,
                trade_mom_lookback=trade_mom_lookback,
                tp_stop=tp_stop,
                sl_stop=sl_stop,
                max_hold=max_hold,
                rsi_window=rsi_window,
                variant_params=variant_params,
                combo_metrics=result["combo_metrics"],
                sym_metrics=result["sym_metrics"],
                metrics=metrics,
                ctx_total_days=ctx["total_days"],
                oos_metrics=result["oos_metrics"],
                config_sha256=config_sha256,
                data_fingerprint=timeframe_data_fingerprint,
            )
            pending_combo_rows.append(combo_row)

        def eval_combo(
            regime,
            indicator_combo,
            combo_params,
            vol_lookback,
            vol_z,
            mom_lookback,
            trade_mom_lookback,
            tp_stop,
            sl_stop,
            max_hold,
            stage,
        ):
            nonlocal done, skipped
            _wait_if_paused(stage)
            combo_key, task_payload = _build_combo_task(
                regime=regime,
                indicator_combo=indicator_combo,
                combo_params=combo_params,
                vol_lookback=vol_lookback,
                vol_z=vol_z,
                mom_lookback=mom_lookback,
                trade_mom_lookback=trade_mom_lookback,
                tp_stop=tp_stop,
                sl_stop=sl_stop,
                max_hold=max_hold,
            )
            if combo_key in seen_keys:
                skipped += 1
                done += 1
                emit_progress(stage=stage)
                return

            result = autowfo_evaluator.evaluate_combo_task(task_payload, runtime_eval)
            _append_eval_result(result, task_payload)
            seen_keys.add(combo_key)
            done += 1
            emit_progress(stage=stage)
            _checkpoint()

        def _on_refine_plan(fine_total, stage):
            nonlocal total_combos
            total_combos += fine_total
            emit_progress(stage=stage, force=True)

        if search_mode == "combo" and max_workers > 1:
            stage = f"{stage_prefix} combo"
            planned_keys = set()
            combo_tasks = []
            for (
                regime,
                combo_keys,
                combo_params,
                vol_lookback,
                vol_z,
                mom_lookback,
                trade_mom_lookback,
                tp_stop,
                sl_stop,
                max_hold,
            ) in autowfo_engine._iter_coarse_plan(
                regime_variants=regime_variants,
                mom_lookbacks=mom_lookbacks,
                vol_lookbacks=vol_lookbacks,
                vol_zs=vol_zs,
                trade_mom_lookbacks=trade_mom_lookbacks,
                tp_stops=tp_stops,
                sl_stops=sl_stops,
                max_holds=max_holds,
                combo_keys_all=combo_keys_all,
                iter_indicator_param_combos_fn=autowfo_strategy._iter_indicator_param_combos,
                indicator_param_options=indicator_param_options,
            ):
                combo_key, task_payload = _build_combo_task(
                    regime=regime,
                    indicator_combo=combo_keys,
                    combo_params=combo_params,
                    vol_lookback=vol_lookback,
                    vol_z=vol_z,
                    mom_lookback=mom_lookback,
                    trade_mom_lookback=trade_mom_lookback,
                    tp_stop=tp_stop,
                    sl_stop=sl_stop,
                    max_hold=max_hold,
                )
                if combo_key in seen_keys or combo_key in planned_keys:
                    skipped += 1
                    done += 1
                    emit_progress(stage=stage)
                    continue
                planned_keys.add(combo_key)
                combo_tasks.append(task_payload)

            for task_payload, result in zip(
                combo_tasks,
                autowfo_parallel._run_combo_tasks(
                combo_tasks,
                runtime_eval,
                max_workers=max_workers,
                ),
            ):
                _append_eval_result(result, task_payload)
                seen_keys.add(task_payload["combo_key"])
                done += 1
                emit_progress(stage=stage)
                _checkpoint()
        else:
            autowfo_engine._run_search_for_timeframe(
                search_mode=search_mode,
                stage_prefix=stage_prefix,
                timeframe=timeframe,
                regime_variants=regime_variants,
                regime_lookup=regime_lookup,
                mom_lookbacks=mom_lookbacks,
                vol_lookbacks=vol_lookbacks,
                vol_zs=vol_zs,
                trade_mom_lookbacks=trade_mom_lookbacks,
                tp_stops=tp_stops,
                sl_stops=sl_stops,
                max_holds=max_holds,
                combo_keys_all=combo_keys_all,
                iter_indicator_param_combos_fn=autowfo_strategy._iter_indicator_param_combos,
                indicator_param_options=indicator_param_options,
                eval_combo_fn=eval_combo,
                existing_combo_df=existing_combo_df,
                apply_quality_filters_fn=apply_quality_filters,
                sort_by_score_fn=autowfo_ranking._sort_by_score,
                combo_group_fields=combo_group_fields,
                top_n_fine=top_n_fine,
                min_avg_daily_trades_target=min_avg_daily_trades_target,
                indicator_defaults=indicator_defaults,
                expand_float_fn=autowfo_strategy._expand_float,
                safe_float_fn=_safe_float,
                refine_indicator_params_fn=autowfo_strategy._refine_indicator_params,
                safe_int_fn=_safe_int,
                on_refine_plan_fn=_on_refine_plan,
            )

    _checkpoint(force=True)

    combo_df, per_symbol_df = autowfo_engine._load_result_frames(combo_path, per_symbol_path)
    combo_path_run, per_symbol_path_run = autowfo_engine._write_run_snapshot_files(
        combo_df, per_symbol_df, out_dir, run_id
    )

    combo_df_current = autowfo_engine._select_current_combo_df(combo_df, timeframe_configs)
    if combo_df_current.empty:
        print("[warn] No valid combinations evaluated; check data download and filters.")
        return

    filtered, min_avg_daily_trades_filter = autowfo_engine._fallback_activity_filter(
        combo_df_current=combo_df_current,
        min_avg_daily_trades_target=min_avg_daily_trades_target,
        apply_quality_filters_fn=apply_quality_filters,
    )

    top10, _ = autowfo_ranking._top_by_score(filtered, top_n=10, tie_break_avg_hold=True)
    top10_path = os.path.join(out_dir, f"param_sweep_top10_{run_id}.csv")
    top10.to_csv(top10_path, index=False)

    best, best_timeframe, best_data_days = autowfo_engine._pick_best_from_top(
        top_df=top10,
        timeframe_configs=timeframe_configs,
        timeframe_days_map=timeframe_days_map,
        safe_int_fn=_safe_int,
    )
    try:
        best_ctx = autowfo_data._prepare_timeframe_context(
            timeframe=best_timeframe,
            data_days=best_data_days,
            base_symbol=base_symbol,
            trade_symbols=trade_symbols,
            exchange=exchange,
            cache_dir=cache_dir,
            cache_format=cache_format,
            vol_lookbacks=vol_lookbacks,
            mom_lookbacks=mom_lookbacks,
            trade_mom_lookbacks=trade_mom_lookbacks,
            rsi_window=rsi_window,
            bb_window=bb_window,
            bb_alpha=bb_alpha,
            atr_window=atr_window,
            ma_pairs=ma_pairs,
            obv_lookbacks=obv_lookbacks,
            volume_lookbacks=volume_lookbacks,
            roc_lookbacks=roc_lookbacks,
            cmf_lookbacks=cmf_lookbacks,
            mfi_window=mfi_window,
            vroc_lookbacks=vroc_lookbacks,
            ad_lookbacks=ad_lookbacks,
            init_cash_usdt=init_cash_usdt,
            capital_mode=capital_mode,
        )
    except Exception as exc:
        print(f"[warn] best report skipped: {exc}")
        return
    trade_close = best_ctx["trade_close"]
    btc_close = best_ctx["btc_close"]
    btc_high = best_ctx["btc_high"]
    btc_low = best_ctx["btc_low"]
    btc_volume = best_ctx["btc_volume"]
    trade_symbols = best_ctx["trade_symbols"]
    plot_symbol = trade_symbols[0]
    init_cash_btc = best_ctx["init_cash_btc"]
    vol_zscore_by_lb = best_ctx["vol_zscore_by_lb"]
    mom_by_lb = best_ctx["mom_by_lb"]
    trade_mom_by_lb = best_ctx["trade_mom_by_lb"]
    rsi_series = best_ctx["rsi_series"]
    bb_width = best_ctx["bb_width"]
    bb_upper = best_ctx["bb_upper"]
    bb_lower = best_ctx["bb_lower"]
    atr_ratio = best_ctx["atr_ratio"]
    ma_trend_by_pair = best_ctx["ma_trend_by_pair"]
    macd_hist_ratio_series = best_ctx["macd_hist_ratio_series"]
    stoch_k = best_ctx["stoch_k"]
    obv_roc_by_lb = best_ctx["obv_roc_by_lb"]
    volume_zscore_by_lb = best_ctx["volume_zscore_by_lb"]
    roc_by_lb = best_ctx["roc_by_lb"]
    cmf_by_window = best_ctx["cmf_by_window"]
    mfi_by_window = best_ctx["mfi_by_window"]
    mfi_window = best_ctx["mfi_window"]
    vroc_by_lb = best_ctx["vroc_by_lb"]
    ad_roc_by_lb = best_ctx["ad_roc_by_lb"]
    data_range = best_ctx["data_range"]
    scan_timeframes = "; ".join(timeframe_ranges) if timeframe_ranges else ""
    wf_slices = autowfo_split._build_walk_forward_slices(
        trade_close.index, wf_train_days, wf_test_days, wf_step_days
    )
    best_regime = {
        "regime_name": best.get("regime_name"),
        "regime_type": best.get("regime_type"),
        "vol_mode": best.get("vol_mode"),
        "regime_rsi_long": best.get("regime_rsi_long"),
        "regime_rsi_short": best.get("regime_rsi_short"),
    }
    indicator_list = best.get("indicator_list")
    if isinstance(indicator_list, float) and np.isnan(indicator_list):
        indicator_list = ""
    best_indicator_combo = tuple([v for v in str(indicator_list).split(",") if v]) if indicator_list else tuple()
    best_filter_name = best.get("filter_name") or _indicator_combo_label(best_indicator_combo)
    best_params = {}
    for field in INDICATOR_PARAM_FIELDS:
        value = best.get(field)
        best_params[field] = value if pd.notna(value) else None
    best_params = autowfo_strategy._coerce_indicator_params(best_indicator_combo, best_params, best_ctx)

    best_vol_lookback = int(best["vol_lookback"]) if pd.notna(best["vol_lookback"]) else vol_lookbacks[0]
    best_vol_z = float(best["vol_z"]) if pd.notna(best["vol_z"]) else vol_zs[0]
    best_mom_lookback = int(best["mom_lookback"]) if pd.notna(best["mom_lookback"]) else mom_lookbacks[0]
    best_trade_mom_lookback = int(best["trade_mom_lookback"])
    best_tp_stop = float(best["tp_stop"])
    best_sl_stop = float(best["sl_stop"])
    best_max_hold = int(best["max_hold"])

    vol_zscore, _ = autowfo_strategy._pick_series_from_map(vol_zscore_by_lb, best_vol_lookback, vol_lookbacks[0] if vol_lookbacks else None)
    if best_regime["vol_mode"] == "high":
        vol_cond = vol_zscore > best_vol_z
    elif best_regime["vol_mode"] == "low":
        vol_cond = vol_zscore < -best_vol_z
    else:
        vol_cond = pd.Series(True, index=vol_zscore.index)

    # Use the same regime signal builder as eval_combo to avoid duplication
    best_regime_for_resolve = {
        "regime_name": best_regime["regime_name"],
        "regime_type": best_regime["regime_type"],
        "vol_mode": best_regime["vol_mode"],
        "rsi_pair": (best_regime["regime_rsi_long"], best_regime["regime_rsi_short"])
        if best_regime["regime_type"] == "rsi_revert" else None,
    }
    long_regime, short_regime, _, _ = autowfo_engine._resolve_regime_signals(
        regime=best_regime_for_resolve,
        vol_cond=vol_cond,
        ctx=best_ctx,
        mom_lookback=best_mom_lookback,
    )
    trade_mom, _ = autowfo_strategy._pick_series_from_map(
        trade_mom_by_lb,
        best_trade_mom_lookback,
        trade_mom_lookbacks[0] if trade_mom_lookbacks else None,
    )
    long_regime, short_regime, best_params = autowfo_strategy._apply_indicator_combo(
        long_regime,
        short_regime,
        best_indicator_combo,
        best_params,
        best_ctx,
    )

    best_bar_hours = autowfo_metrics._timeframe_to_hours(best_timeframe)
    # Use the same cost computation as eval_combo to guarantee consistency
    best_effective_fees, best_effective_slippage = autowfo_engine._compute_effective_costs(
        fees=fees,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        funding_rate_daily=funding_rate_daily,
        max_hold=best_max_hold,
        bar_hours=best_bar_hours,
    )

    best_pf = autowfo_portfolio._run_pf(
        trade_close,
        long_regime,
        short_regime,
        best_max_hold,
        best_effective_fees,
        best_sl_stop,
        best_tp_stop,
        freq=best_timeframe,
        long_filter=trade_mom > 0,
        short_filter=trade_mom < 0,
        init_cash=init_cash_btc,
        size=order_size_pct,
        size_type="percent",
        cash_sharing=(capital_mode == "shared"),
        lock_cash=True,
        allow_partial=False,
        max_positions=(max_concurrent_positions if capital_mode == "shared" else None),
        long_scores=trade_mom,
        short_scores=-trade_mom,
        slippage=best_effective_slippage,
    )
    fig = autowfo_report._plot_portfolio(best_pf, plot_symbol)
    plot_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    best_metrics = autowfo_metrics._calc_pf_series(best_pf, trade_symbols, autowfo_metrics._timeframe_to_hours(best_timeframe))
    best_summary = pd.DataFrame({
        "symbol": trade_symbols,
        "total_return_pct": (best_metrics["total_return_pct"]).to_numpy(),
        "total_profit": best_metrics["total_profit"].to_numpy(),
        "total_trades": best_metrics["total_trades"].to_numpy(),
        "win_rate_pct": best_metrics["win_rate_pct"].to_numpy(),
        "avg_trade_pct": best_metrics["avg_trade_pct"].to_numpy(),
        "max_drawdown_pct": best_metrics["max_drawdown_pct"].to_numpy(),
        "position_coverage_pct": best_metrics["position_coverage_pct"].to_numpy(),
        "avg_hold_hours": best_metrics["avg_hold_hours"].to_numpy(),
    })

    report_params = pd.DataFrame([{
        "timeframe": best_timeframe,
        "data_days": best_data_days,
        "capital_mode": capital_mode,
        "regime_name": best_regime["regime_name"],
        "regime_type": best_regime["regime_type"],
        "vol_mode": best_regime["vol_mode"],
        "regime_rsi_long": best_regime["regime_rsi_long"],
        "regime_rsi_short": best_regime["regime_rsi_short"],
        "filter_name": best_filter_name,
        "indicator_list": indicator_list,
        "indicator_count": len(best_indicator_combo),
        "vol_lookback": best.get("vol_lookback"),
        "vol_z": best.get("vol_z"),
        "mom_lookback": best.get("mom_lookback"),
        "trade_mom_lookback": best_trade_mom_lookback,
        "tp_stop": best_tp_stop,
        "sl_stop": best_sl_stop,
        "max_hold": best_max_hold,
        "rsi_window": rsi_window if "rsi" in best_indicator_combo else None,
        "rsi_long": best_params["rsi_long"],
        "rsi_short": best_params["rsi_short"],
        "bb_width": best_params["bb_width"],
        "atr_ratio": best_params["atr_ratio"],
        "ma_fast": best_params["ma_fast"],
        "ma_slow": best_params["ma_slow"],
        "macd_hist_ratio": best_params["macd_hist_ratio"],
        "stoch_long": best_params["stoch_long"],
        "stoch_short": best_params["stoch_short"],
        "obv_lookback": best_params["obv_lookback"],
        "volume_lookback": best_params["volume_lookback"],
        "volume_z": best_params["volume_z"],
        "roc_lookback": best_params["roc_lookback"],
        "roc_threshold": best_params["roc_threshold"],
        "mfi_long": best_params["mfi_long"],
        "mfi_short": best_params["mfi_short"],
        "cmf_lookback": best_params["cmf_lookback"],
        "cmf_threshold": best_params["cmf_threshold"],
        "vroc_lookback": best_params["vroc_lookback"],
        "vroc_threshold": best_params["vroc_threshold"],
        "ad_lookback": best_params["ad_lookback"],
    }])

    oos_summary = pd.DataFrame([{
        "oos_segments": best.get("oos_segments"),
        "oos_avg_total_return_pct": best.get("oos_avg_total_return_pct"),
        "oos_avg_win_rate_pct": best.get("oos_avg_win_rate_pct"),
        "oos_avg_avg_trade_pct": best.get("oos_avg_avg_trade_pct"),
        "oos_avg_max_drawdown_pct": best.get("oos_avg_max_drawdown_pct"),
        "oos_avg_position_coverage_pct": best.get("oos_avg_position_coverage_pct"),
        "oos_avg_total_trades": best.get("oos_avg_total_trades"),
        "oos_min_total_trades": best.get("oos_min_total_trades"),
        "oos_avg_daily_trades": best.get("oos_avg_daily_trades"),
        "oos_avg_hold_hours": best.get("oos_avg_hold_hours"),
    }])

    top_columns = [
        "timeframe",
        "data_days",
        "regime_name",
        "regime_type",
        "vol_mode",
        "regime_rsi_long",
        "regime_rsi_short",
        "filter_name",
        "indicator_list",
        "indicator_count",
        "vol_lookback",
        "vol_z",
        "mom_lookback",
        "trade_mom_lookback",
        "tp_stop",
        "sl_stop",
        "max_hold",
        "rsi_window",
        "rsi_long",
        "rsi_short",
        "bb_width",
        "atr_ratio",
        "ma_fast",
        "ma_slow",
        "macd_hist_ratio",
        "stoch_long",
        "stoch_short",
        "obv_lookback",
        "volume_lookback",
        "volume_z",
        "roc_lookback",
        "roc_threshold",
        "mfi_long",
        "mfi_short",
        "cmf_lookback",
        "cmf_threshold",
        "vroc_lookback",
        "vroc_threshold",
        "ad_lookback",
        "avg_total_return_pct",
        "avg_daily_trades",
        "avg_hold_hours",
        "oos_avg_total_return_pct",
        "oos_avg_win_rate_pct",
        "oos_avg_avg_trade_pct",
        "oos_avg_max_drawdown_pct",
        "oos_avg_position_coverage_pct",
        "oos_avg_total_trades",
        "oos_min_total_trades",
        "oos_avg_daily_trades",
        "oos_avg_hold_hours",
        "oos_segments",
        "avg_win_rate_pct",
        "avg_avg_trade_pct",
        "avg_max_drawdown_pct",
        "avg_position_coverage_pct",
        "avg_total_trades",
        "min_total_trades",
    ]

    summary_columns = [
        "symbol",
        "total_return_pct",
        "total_profit",
        "total_trades",
        "position_coverage_pct",
        "win_rate_pct",
        "avg_trade_pct",
        "max_drawdown_pct",
        "avg_hold_hours",
    ]

    report_params_html = _df_to_html(report_params, list(report_params.columns), LABELS)
    oos_summary_html = _df_to_html(oos_summary, list(oos_summary.columns), LABELS)
    top10_html = _df_to_html(top10, top_columns, LABELS)
    summary_html = _df_to_html(best_summary, summary_columns, LABELS)

    # Persist this run into a simple leaderboard for long-term iteration.
    report_file_latest = f"btc_regime_{plot_symbol.replace('/', '-')}.html"
    report_file_run = f"btc_regime_{plot_symbol.replace('/', '-')}_{run_id}.html"
    report_path_latest = os.path.join(out_dir, report_file_latest)
    report_path_run = os.path.join(out_dir, report_file_run)

    leaderboard_row = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "config_sha256": config_sha256,
        "data_fingerprint": best.get("data_fingerprint"),
        "plot_symbol": plot_symbol,
        "timeframe": best_timeframe,
        "data_days": best_data_days,
        "min_avg_daily_trades_target": min_avg_daily_trades_target,
        "min_avg_daily_trades_filter": min_avg_daily_trades_filter,
        "capital_mode": capital_mode,
        "init_cash_usdt": init_cash_usdt,
        "order_size_pct": order_size_pct,
        "max_concurrent_positions": max_concurrent_positions,
        "slippage_bps": slippage_bps,
        "spread_bps": spread_bps,
        "funding_rate_daily": funding_rate_daily,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "wf_segments": len(wf_slices),
        "regime_name": best.get("regime_name"),
        "regime_type": best.get("regime_type"),
        "vol_mode": best.get("vol_mode"),
        "regime_rsi_long": best.get("regime_rsi_long"),
        "regime_rsi_short": best.get("regime_rsi_short"),
        "filter_name": best.get("filter_name"),
        "indicator_list": best.get("indicator_list"),
        "indicator_count": best.get("indicator_count"),
        "vol_lookback": best.get("vol_lookback"),
        "vol_z": best.get("vol_z"),
        "mom_lookback": best.get("mom_lookback"),
        "trade_mom_lookback": best.get("trade_mom_lookback"),
        "tp_stop": best.get("tp_stop"),
        "sl_stop": best.get("sl_stop"),
        "max_hold": best.get("max_hold"),
        "rsi_window": best.get("rsi_window"),
        "rsi_long": best.get("rsi_long"),
        "rsi_short": best.get("rsi_short"),
        "bb_width": best.get("bb_width"),
        "atr_ratio": best.get("atr_ratio"),
        "ma_fast": best.get("ma_fast"),
        "ma_slow": best.get("ma_slow"),
        "macd_hist_ratio": best.get("macd_hist_ratio"),
        "stoch_long": best.get("stoch_long"),
        "stoch_short": best.get("stoch_short"),
        "obv_lookback": best.get("obv_lookback"),
        "volume_lookback": best.get("volume_lookback"),
        "volume_z": best.get("volume_z"),
        "roc_lookback": best.get("roc_lookback"),
        "roc_threshold": best.get("roc_threshold"),
        "mfi_long": best.get("mfi_long"),
        "mfi_short": best.get("mfi_short"),
        "cmf_lookback": best.get("cmf_lookback"),
        "cmf_threshold": best.get("cmf_threshold"),
        "vroc_lookback": best.get("vroc_lookback"),
        "vroc_threshold": best.get("vroc_threshold"),
        "ad_lookback": best.get("ad_lookback"),
        "avg_total_return_pct": best.get("avg_total_return_pct"),
        "avg_daily_trades": best.get("avg_daily_trades"),
        "avg_hold_hours": best.get("avg_hold_hours"),
        "avg_position_coverage_pct": best.get("avg_position_coverage_pct"),
        "avg_total_trades": best.get("avg_total_trades"),
        "min_total_trades": best.get("min_total_trades"),
        "oos_avg_total_return_pct": best.get("oos_avg_total_return_pct"),
        "oos_avg_win_rate_pct": best.get("oos_avg_win_rate_pct"),
        "oos_avg_avg_trade_pct": best.get("oos_avg_avg_trade_pct"),
        "oos_avg_max_drawdown_pct": best.get("oos_avg_max_drawdown_pct"),
        "oos_avg_position_coverage_pct": best.get("oos_avg_position_coverage_pct"),
        "oos_avg_total_trades": best.get("oos_avg_total_trades"),
        "oos_min_total_trades": best.get("oos_min_total_trades"),
        "oos_avg_daily_trades": best.get("oos_avg_daily_trades"),
        "oos_avg_hold_hours": best.get("oos_avg_hold_hours"),
        "oos_segments": best.get("oos_segments"),
        "report_file": report_file_run,
    }

    lb_df = autowfo_engine._append_leaderboard_row(
        leaderboard_path=leaderboard_path,
        leaderboard_row=leaderboard_row,
    )
    lb_view, lb_recent, lb_best = autowfo_engine._build_leaderboard_views(
        lb_df=lb_df,
        history_rows=history_rows,
        top_by_score_fn=autowfo_ranking._top_by_score,
    )
    lb_cols = [
        "timestamp_utc",
        "run_id",
        "config_sha256",
        "plot_symbol",
        "timeframe",
        "data_days",
        "min_avg_daily_trades_target",
        "min_avg_daily_trades_filter",
        "regime_name",
        "regime_type",
        "oos_avg_total_return_pct",
        "avg_total_return_pct",
        "avg_daily_trades",
        "oos_avg_daily_trades",
        "avg_total_trades",
        "avg_position_coverage_pct",
        "min_total_trades",
        "filter_name",
        "report",
    ]
    lb_recent_html = _df_to_html(lb_recent.reindex(columns=lb_cols), lb_cols, LABELS)
    lb_best_html = _df_to_html(lb_best.reindex(columns=lb_cols), lb_cols, LABELS)

    scan_timeframes_html = (
        f"<div><strong>{LABELS['scan_timeframes']}:</strong> {scan_timeframes}</div>"
        if scan_timeframes
        else ""
    )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>BTC Regime Backtest</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
    h1, h2 {{ margin: 16px 0 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
    th {{ background: #f3f3f3; text-align: right; }}
    td:first-child, th:first-child {{ text-align: left; }}
    .meta {{ background: #fafafa; border: 1px solid #eee; padding: 12px; }}
  </style>
</head>
<body>
  <h1>{LABELS['report_title']}</h1>
    <div class="meta">
    <div><strong>{LABELS['data_range']}:</strong> {data_range}</div>
    <div><strong>{LABELS['timeframe']}:</strong> {best_timeframe}</div>
    <div><strong>{LABELS['data_days']}:</strong> {best_data_days}</div>
    {scan_timeframes_html}
    <div><strong>{LABELS['run_id']}:</strong> {run_id}</div>
    <div><strong>{LABELS['timestamp_utc']}:</strong> {timestamp_utc}</div>
    <div><strong>{LABELS['min_avg_daily_trades_target']}:</strong> {min_avg_daily_trades_target}</div>
    <div><strong>{LABELS['min_avg_daily_trades_filter']}:</strong> {min_avg_daily_trades_filter}</div>
    <div><strong>{LABELS['capital_mode']}:</strong> {capital_mode}</div>
    <div><strong>{LABELS['init_cash_usdt']}:</strong> {init_cash_usdt}</div>
    <div><strong>{LABELS['order_size_pct']}:</strong> {order_size_pct}</div>
    <div><strong>{LABELS['max_concurrent_positions']}:</strong> {max_concurrent_positions}</div>
    <div><strong>{LABELS['wf_train_days']}:</strong> {wf_train_days}</div>
    <div><strong>{LABELS['wf_test_days']}:</strong> {wf_test_days}</div>
    <div><strong>{LABELS['wf_step_days']}:</strong> {wf_step_days}</div>
    <div><strong>{LABELS['wf_segments']}:</strong> {len(wf_slices)}</div>
    <div><strong>{LABELS['base_symbol']}:</strong> {base_symbol}</div>
    <div><strong>{LABELS['trade_symbols']}:</strong> {', '.join(trade_symbols)}</div>
  </div>

  <h2>{LABELS['summary_title']}</h2>
  {summary_html}

  <h2>{LABELS['params_title']}</h2>
  {report_params_html}

  <h2>{LABELS['oos_summary_title']}</h2>
  {oos_summary_html}

  <h2>{LABELS['top_title']}</h2>
  {top10_html}

  <h2>{LABELS['history_title']}</h2>

  <h2>{LABELS['leaderboard_title']}</h2>
  {lb_best_html}

  <h2>{LABELS['recent_runs_title']}</h2>
  {lb_recent_html}

  <h2>{LABELS['chart_title']} ({plot_symbol})</h2>
  {plot_html}
</body>
</html>
"""

    with open(report_path_latest, "w", encoding="utf-8") as f:
        f.write(html)
    with open(report_path_run, "w", encoding="utf-8") as f:
        f.write(html)

    run_data_fingerprint = autowfo_artifacts._combine_data_fingerprints(timeframe_fingerprints)
    run_metadata_payload = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "search_mode": search_mode,
        "config_sha256": config_sha256,
        "data_fingerprint": run_data_fingerprint,
        "config_path": config_path,
        "exchange": exchange,
        "base_symbol": base_symbol,
        "trade_symbols": trade_symbols,
        "timeframes": timeframe_configs,
        "wf_train_days": wf_train_days,
        "wf_test_days": wf_test_days,
        "wf_step_days": wf_step_days,
        "capital_mode": capital_mode,
        "init_cash_usdt": init_cash_usdt,
    }
    autowfo_artifacts._write_run_metadata(run_metadata_path, run_metadata_payload)
    autowfo_artifacts._write_run_metadata(run_metadata_path_run, run_metadata_payload)

    emit_progress(stage="complete", force=True)

    print("combo_summary", combo_path)
    print("per_symbol_summary", per_symbol_path)
    print("top10", top10_path)
    print("leaderboard", leaderboard_path)
    print("run_metadata", run_metadata_path)
    print("run_metadata_run", run_metadata_path_run)
    print("report_latest", report_path_latest)
    print("report_run", report_path_run)


if __name__ == "__main__":
    main()

