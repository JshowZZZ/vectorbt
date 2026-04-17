"""Freqtrade bridge helpers for frozen AUTOWFO pilot lanes."""

from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from autowfo import data as autowfo_data
from autowfo import engine_helpers
from autowfo import engine_runtime
from autowfo import evaluator as autowfo_evaluator
from autowfo import metrics as autowfo_metrics
from autowfo import pilot_analysis
from autowfo import portfolio as autowfo_portfolio
from autowfo import strategy as autowfo_strategy
from autowfo.constants import INDICATOR_META, INDICATOR_PARAM_FIELDS


SIGNAL_STORE_SCHEMA_VERSION = "1.0.0"
SIGNAL_BUNDLE_MANIFEST_VERSION = "1.0.0"
DEFAULT_SIGNAL_STORE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "plans" / "protocols" / "awf327_signal_store_schema.json"
)
DEFAULT_RSI_REVERT_PAIRS = ((30, 70), (35, 65), (40, 60))
DEFAULT_RSI_WINDOW = 14
DEFAULT_BB_WINDOW = 20
DEFAULT_BB_ALPHA = 2
DEFAULT_ATR_WINDOW = 14
DEFAULT_MFI_WINDOW = 14
DEFAULT_ULTOSC_PERIODS = (7, 14, 28)
DEFAULT_PPO_FAST = 12
DEFAULT_PPO_SLOW = 26
DEFAULT_PPO_SIGNAL = 9
DEFAULT_FEES = 0.001
DEFAULT_SIGNAL_COLUMNS = (
    "signal_long",
    "signal_short",
    "enter_long",
    "enter_short",
    "exit_long",
    "exit_short",
    "explicit_exit_long",
    "explicit_exit_short",
)
DEFAULT_ANALYSIS_SELECTIONS = {
    "canonical": "canonical_gate_passed",
    "canonical_gate_passed": "canonical_gate_passed",
    "gate": "top_gate_passed",
    "top_gate_passed": "top_gate_passed",
    "stable": "top_stable_positive",
    "top_stable_positive": "top_stable_positive",
    "all": "compared_rows",
    "compared_rows": "compared_rows",
}


def _split_pair_components(pair: Any) -> tuple[str, str | None]:
    text = str(pair or "").strip()
    if not text:
        return "", None
    symbol_part = text.split(":", 1)[0]
    if "/" not in symbol_part:
        return text, None
    base, quote = symbol_part.split("/", 1)
    return base.strip(), quote.strip() or None


def _build_usdt_perpetual_pair(base: str) -> str:
    resolved_base = str(base or "").strip()
    if not resolved_base:
        raise ValueError("base asset is required to build a USDT perpetual pair")
    return f"{resolved_base}/USDT:USDT"


def _default_execution_pair_mapping(source_pairs: Sequence[str], *, trading_mode: str) -> dict[str, str]:
    resolved_mode = str(trading_mode or "spot").strip().lower()
    if resolved_mode != "futures":
        return {}
    mapping: dict[str, str] = {}
    for source_pair in source_pairs:
        pair_text = str(source_pair or "").strip()
        if not pair_text:
            continue
        base, _ = _split_pair_components(pair_text)
        if not base:
            continue
        mapping[pair_text] = _build_usdt_perpetual_pair(base)
    return mapping


def _resolve_pair_mapping(
    manifest: Mapping[str, Any],
    *,
    trading_mode: str,
) -> dict[str, str]:
    source = dict(manifest.get("source") or {})
    freqtrade = dict(manifest.get("freqtrade") or {})
    raw_mapping = freqtrade.get("autowfo_pair_mapping") or {}
    if isinstance(raw_mapping, Mapping):
        cleaned = {
            str(source_pair).strip(): str(exec_pair).strip()
            for source_pair, exec_pair in raw_mapping.items()
            if str(source_pair).strip() and str(exec_pair).strip()
        }
        if cleaned:
            return cleaned
    return _default_execution_pair_mapping(list(source.get("pairs") or []), trading_mode=trading_mode)


def _resolve_execution_pairs(source_pairs: Sequence[str], pair_mapping: Mapping[str, str]) -> list[str]:
    resolved_pairs: list[str] = []
    for source_pair in source_pairs:
        pair_text = str(source_pair or "").strip()
        if not pair_text:
            continue
        execution_pair = str(pair_mapping.get(pair_text) or pair_text).strip()
        if execution_pair and execution_pair not in resolved_pairs:
            resolved_pairs.append(execution_pair)
    return resolved_pairs


def _resolve_execution_quote_currency(execution_pairs: Sequence[str], fallback: str) -> str:
    for pair in execution_pairs:
        _, quote = _split_pair_components(pair)
        if quote:
            return quote
    return str(fallback or "USDT")


def _normalize_trade_pairs(trades_df: pd.DataFrame, pair_mapping: Mapping[str, str]) -> pd.DataFrame:
    normalized = trades_df.copy()
    reverse_mapping = {str(target): str(source) for source, target in pair_mapping.items()}
    if reverse_mapping and "pair" in normalized.columns:
        normalized["pair"] = normalized["pair"].astype(str).map(lambda value: reverse_mapping.get(value, value))
    return normalized


def _resolve_backtest_result_path(backtest_directory: str | Path) -> Path:
    result_dir = Path(backtest_directory).resolve()
    for pointer_name in (".last_result.json", "latest-backtest.json"):
        pointer_path = result_dir / pointer_name
        if pointer_path.exists():
            try:
                latest_payload = json.loads(pointer_path.read_text(encoding="utf-8-sig"))
            except Exception:
                latest_payload = None
            candidate_text = None
            if isinstance(latest_payload, str):
                candidate_text = latest_payload
            elif isinstance(latest_payload, Mapping):
                for key in ("latest_backtest", "filename", "backtest_result"):
                    value = latest_payload.get(key)
                    if value not in (None, ""):
                        candidate_text = str(value)
                        break
            if candidate_text:
                candidate_path = Path(candidate_text)
                if not candidate_path.is_absolute():
                    candidate_path = (result_dir / candidate_path).resolve()
                if candidate_path.exists():
                    return candidate_path
    latest_path = result_dir / "latest-backtest.json"
    if latest_path.exists():
        try:
            latest_payload = json.loads(latest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            latest_payload = None
        candidate_text = None
        if isinstance(latest_payload, str):
            candidate_text = latest_payload
        elif isinstance(latest_payload, Mapping):
            for key in ("latest_backtest", "filename", "backtest_result"):
                value = latest_payload.get(key)
                if value not in (None, ""):
                    candidate_text = str(value)
                    break
        if candidate_text:
            candidate_path = Path(candidate_text)
            if not candidate_path.is_absolute():
                candidate_path = (result_dir / candidate_path).resolve()
            if candidate_path.exists():
                return candidate_path
    candidates = sorted(
        [
            path
            for path in result_dir.glob("*.json")
            if path.name not in {"freqtrade_backtest_config.json", "parity_report.json", "latest-backtest.json"}
        ],
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(payload, Mapping) and isinstance(payload.get("strategy"), Mapping):
            return candidate
    raise FileNotFoundError(f"Freqtrade backtest result not found under {result_dir}")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        result = float(value)
        return None if np.isnan(result) else result
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(result) else result


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if np.isnan(result):
            return None
        return int(result)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    return True


def _strip_none_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if _has_value(value)}


def _split_indicator_text(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    return [token.strip() for token in str(value).split(",") if token and str(token).strip()]


def _normalize_timestamp_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="coerce").dt.tz_localize(None)


def _normalize_timestamp_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.tz_localize(None).isoformat()


def _analysis_bucket_name(selection: str) -> str:
    key = str(selection or "canonical").strip().lower()
    if key not in DEFAULT_ANALYSIS_SELECTIONS:
        raise ValueError(f"unknown analysis selection: {selection}")
    return DEFAULT_ANALYSIS_SELECTIONS[key]


def select_analysis_candidate(
    analysis_payload: Mapping[str, Any],
    *,
    selection: str = "canonical",
    rank: int = 1,
) -> dict[str, Any]:
    bucket_name = _analysis_bucket_name(selection)
    rows = list(analysis_payload.get(bucket_name) or [])
    if not rows:
        raise ValueError(f"analysis report has no rows in {bucket_name}")
    if rank <= 0:
        raise ValueError("rank must be >= 1")
    index = rank - 1
    if index >= len(rows):
        raise ValueError(f"rank {rank} is out of range for {bucket_name} ({len(rows)} rows)")
    selected = dict(rows[index])
    selected["analysis_bucket"] = bucket_name
    selected["analysis_rank"] = rank
    return selected


def load_signal_store_schema(path: str | Path | None = None) -> dict[str, Any]:
    schema_path = Path(path) if path is not None else DEFAULT_SIGNAL_STORE_SCHEMA_PATH
    if not schema_path.exists():
        raise ValueError(f"signal store schema file not found: {schema_path}")
    payload = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    validate_signal_store_schema(payload, source=str(schema_path))
    return payload


def validate_signal_store_schema(payload: object, *, source: str = "<in-memory>") -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"signal store schema must be a JSON object: {source}")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError(f"schema_version is required: {source}")
    signal_columns = payload.get("signal_columns")
    if not isinstance(signal_columns, list) or not signal_columns:
        raise ValueError(f"signal_columns must be a non-empty list: {source}")
    required_signal_columns = payload.get("required_signal_columns")
    if not isinstance(required_signal_columns, list) or not required_signal_columns:
        raise ValueError(f"required_signal_columns must be a non-empty list: {source}")
    required_manifest_paths = payload.get("required_manifest_paths")
    if not isinstance(required_manifest_paths, list) or not required_manifest_paths:
        raise ValueError(f"required_manifest_paths must be a non-empty list: {source}")


def validate_signal_store_frame(
    signal_df: pd.DataFrame,
    *,
    schema_payload: Mapping[str, Any] | None = None,
) -> None:
    schema = schema_payload or load_signal_store_schema()
    required_columns = list(schema.get("required_signal_columns") or [])
    missing_columns = [column for column in required_columns if column not in signal_df.columns]
    if missing_columns:
        raise ValueError(f"signal store is missing required columns: {missing_columns}")


def validate_signal_bundle_manifest(
    manifest: Mapping[str, Any],
    *,
    schema_payload: Mapping[str, Any] | None = None,
) -> None:
    schema = schema_payload or load_signal_store_schema()
    required_paths = list(schema.get("required_manifest_paths") or [])
    missing_paths = []
    for dotted_path in required_paths:
        cursor: Any = manifest
        for key in str(dotted_path).split("."):
            if not isinstance(cursor, Mapping) or key not in cursor:
                cursor = None
                break
            cursor = cursor[key]
        if cursor in (None, ""):
            missing_paths.append(dotted_path)
    if missing_paths:
        raise ValueError(f"signal bundle manifest is missing required fields: {missing_paths}")


def _load_base_config(main_run: Mapping[str, Any], *, cwd: str | Path | None = None) -> tuple[dict[str, Any], Path | None]:
    metadata = dict(main_run.get("metadata") or {})
    config_path = pilot_analysis._resolve_base_config_path(metadata.get("config_path"), cwd=cwd)
    if config_path is None or not config_path.exists():
        return {}, None
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return {}, config_path
    return dict(payload), config_path


def _load_runtime_defaults(main_run: Mapping[str, Any], *, cwd: str | Path | None = None) -> dict[str, Any]:
    metadata = dict(main_run.get("metadata") or {})
    base_config, _ = _load_base_config(main_run, cwd=cwd)
    default_config = dict(engine_helpers.DEFAULT_CONFIG)
    default_config.update(base_config)
    if metadata.get("trade_symbols"):
        default_config["trade_symbols"] = list(metadata.get("trade_symbols") or [])
    if metadata.get("timeframes"):
        default_config["timeframes"] = list(metadata.get("timeframes") or [])
    for field in (
        "wf_train_days",
        "wf_test_days",
        "wf_step_days",
        "wf_valid_days",
        "wf_mode",
        "capital_mode",
        "init_cash_usdt",
        "slippage_bps",
        "spread_bps",
        "funding_rate_daily",
        "order_size_pct",
        "max_concurrent_positions",
        "exchange",
        "base_symbol",
        "open_interest_provider",
        "risk_mode",
        "pilot_fixed_indicator_params",
        "pilot_single_trend_mom",
        "strategy_mode",
        "state_exit_policy",
        "regime_preset",
    ):
        value = metadata.get(field)
        if value not in (None, ""):
            default_config[field] = value
    return default_config


def _active_indicator_keys(selected_row: Mapping[str, Any]) -> list[str]:
    strategy_mode = str(selected_row.get("strategy_mode") or "combo_entry").strip().lower()
    if strategy_mode == "state_trigger_entry":
        ordered: list[str] = []
        for value in (
            *_split_indicator_text(selected_row.get("state_indicator_list")),
            *_split_indicator_text(selected_row.get("trigger_indicator_list")),
        ):
            if value not in ordered:
                ordered.append(value)
        if ordered:
            return ordered
    return _split_indicator_text(selected_row.get("indicator_list"))


def _combo_indicator_keys(selected_row: Mapping[str, Any]) -> tuple[str, ...]:
    indicator_keys = _split_indicator_text(selected_row.get("indicator_list"))
    if indicator_keys:
        return tuple(indicator_keys)
    return tuple(_active_indicator_keys(selected_row))


def _state_indicator_keys(selected_row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_split_indicator_text(selected_row.get("state_indicator_list")))


def _trigger_indicator_keys(selected_row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_split_indicator_text(selected_row.get("trigger_indicator_list")))


def _indicator_default_payload(indicator_keys: Sequence[str]) -> dict[str, dict[str, Any]]:
    options = autowfo_strategy._build_indicator_param_options_coarse()
    filtered = {key: list(options.get(key, [{}])) for key in indicator_keys}
    return autowfo_strategy._indicator_defaults(filtered)


def _build_combo_params(selected_row: Mapping[str, Any], *, pilot_fixed_indicator_params: bool) -> dict[str, Any]:
    combo_params = {
        field: selected_row.get(field)
        for field in INDICATOR_PARAM_FIELDS
        if _has_value(selected_row.get(field))
    }
    active_indicators = _active_indicator_keys(selected_row)
    defaults = _indicator_default_payload(active_indicators)
    missing_fields: list[str] = []
    for indicator_key in active_indicators:
        for field, default_value in dict(defaults.get(indicator_key) or {}).items():
            if _has_value(combo_params.get(field)):
                continue
            if pilot_fixed_indicator_params:
                combo_params[field] = default_value
            else:
                missing_fields.append(field)
    if missing_fields:
        unique_missing = sorted(set(missing_fields))
        raise ValueError(
            "selected row is missing replay-critical indicator params; "
            f"either use a run with pilot_fixed_indicator_params=true or persist these fields: {unique_missing}"
        )
    return combo_params


def _collect_overlay_requirements(filter_spec: Mapping[str, Any]) -> dict[str, list[Any]]:
    htf_timeframes: list[str] = []
    htf_windows: list[int] = []
    funding_long_thresholds: list[float] = []
    funding_short_thresholds: list[float] = []

    def _visit(spec: Mapping[str, Any]) -> None:
        kind = str(spec.get("kind") or "").strip().lower()
        if kind == "composite":
            for child in list(spec.get("filters") or []):
                if isinstance(child, Mapping):
                    _visit(child)
            return
        if kind == "htf_trend":
            timeframe = str(spec.get("timeframe") or "").strip().lower()
            window = _safe_int(spec.get("window"))
            if timeframe and timeframe not in htf_timeframes:
                htf_timeframes.append(timeframe)
            if window is not None and window not in htf_windows:
                htf_windows.append(window)
            return
        if kind == "funding_gate":
            long_threshold = _safe_float(spec.get("long_threshold"))
            short_threshold = _safe_float(spec.get("short_threshold"))
            if long_threshold is not None and long_threshold not in funding_long_thresholds:
                funding_long_thresholds.append(long_threshold)
            if short_threshold is not None and short_threshold not in funding_short_thresholds:
                funding_short_thresholds.append(short_threshold)

    _visit(filter_spec)
    return {
        "htf_trend_timeframes": htf_timeframes,
        "htf_trend_windows": htf_windows,
        "funding_gate_long_thresholds": funding_long_thresholds,
        "funding_gate_short_thresholds": funding_short_thresholds,
    }


def _resolve_timeframe_config(main_run: Mapping[str, Any], *, selected_row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(main_run.get("metadata") or {})
    timeframe = str(selected_row.get("timeframe") or "").strip()
    data_days = _safe_int(selected_row.get("data_days"))
    for config in list(metadata.get("timeframes") or []):
        if not isinstance(config, Mapping):
            continue
        if str(config.get("timeframe") or "").strip() != timeframe:
            continue
        candidate_days = _safe_int(config.get("days"))
        if data_days is None or candidate_days == data_days:
            return dict(config)
    payload: dict[str, Any] = {"timeframe": timeframe}
    if data_days is not None:
        payload["days"] = data_days
    return payload


def _resolve_timeframe_config_for_mode(
    main_run: Mapping[str, Any],
    *,
    selected_row: Mapping[str, Any],
    rolling_window: bool = False,
) -> dict[str, Any]:
    if not rolling_window:
        return _resolve_timeframe_config(main_run, selected_row=selected_row)
    timeframe = str(selected_row.get("timeframe") or "").strip()
    data_days = _safe_int(selected_row.get("data_days"))
    payload: dict[str, Any] = {"timeframe": timeframe}
    if data_days is not None:
        payload["days"] = data_days
    return payload


def _resolve_runtime_context(
    main_run: Mapping[str, Any],
    *,
    selected_row: Mapping[str, Any],
    cwd: str | Path | None = None,
    rolling_window: bool = False,
) -> dict[str, Any]:
    metadata = dict(main_run.get("metadata") or {})
    default_config = _load_runtime_defaults(main_run, cwd=cwd)
    base_symbol = str(metadata.get("base_symbol") or default_config.get("base_symbol") or "BTC/USDT")
    default_trade_symbols = list(metadata.get("trade_symbols") or default_config.get("trade_symbols") or [])
    runtime_settings = engine_helpers._resolve_runtime_settings(
        default_config=default_config,
        base_symbol=base_symbol,
        default_trade_symbols=default_trade_symbols,
        available_indicator_keys=list(INDICATOR_META.keys()),
        normalize_split_mode_fn=lambda value: str(value or "anchored").strip().lower(),
        resolve_ranking_config_fn=lambda value: value,
    )
    timeframe_config = _resolve_timeframe_config_for_mode(
        main_run,
        selected_row=selected_row,
        rolling_window=rolling_window,
    )
    filter_spec = engine_runtime._parse_overlay_filter_name(selected_row.get("filter_name"))
    overlay_requirements = _collect_overlay_requirements(filter_spec)
    combo_params = _build_combo_params(
        selected_row,
        pilot_fixed_indicator_params=bool(runtime_settings.get("pilot_fixed_indicator_params", False)),
    )

    active_indicators = _active_indicator_keys(selected_row)
    combo_indicator_keys = _combo_indicator_keys(selected_row)
    state_indicator_combo = _state_indicator_keys(selected_row)
    trigger_indicator_combo = _trigger_indicator_keys(selected_row)
    vol_lookback = _safe_int(selected_row.get("vol_lookback")) or 24
    mom_lookback = _safe_int(selected_row.get("mom_lookback")) or 6
    trade_mom_lookback = _safe_int(selected_row.get("trade_mom_lookback")) or 3
    bar_hours = autowfo_metrics._timeframe_to_hours(str(timeframe_config.get("timeframe") or selected_row.get("timeframe") or "2h"))

    def _lookback_values(field: str, indicator_key: str) -> list[int]:
        if indicator_key not in active_indicators:
            return []
        value = _safe_int(combo_params.get(field))
        return [value] if value is not None else []

    ma_fast = _safe_int(combo_params.get("ma_fast"))
    ma_slow = _safe_int(combo_params.get("ma_slow"))
    ma_pairs = []
    if "ma_trend" in active_indicators and ma_fast is not None and ma_slow is not None:
        ma_pairs = [(ma_fast, ma_slow)]
    if not ma_pairs:
        ma_pairs = engine_helpers._build_ma_pairs([(10, 30), (20, 50)])

    ctx = autowfo_data._prepare_timeframe_context(
        timeframe=str(timeframe_config.get("timeframe") or selected_row.get("timeframe") or "2h"),
        data_days=int(timeframe_config.get("days") or selected_row.get("data_days") or 180),
        data_start=timeframe_config.get("start"),
        data_end=timeframe_config.get("end"),
        base_symbol=base_symbol,
        trade_symbols=list(metadata.get("trade_symbols") or runtime_settings.get("trade_symbols") or []),
        exchange=str(metadata.get("exchange") or default_config.get("exchange") or "binance"),
        cache_dir=str((Path(cwd or ".").resolve() / "artifacts" / "cache_ccxt")),
        cache_format="parquet" if autowfo_data._has_parquet_engine() else "csv",
        vol_lookbacks=[vol_lookback],
        mom_lookbacks=[mom_lookback],
        trade_mom_lookbacks=[trade_mom_lookback],
        rsi_window=_safe_int(selected_row.get("rsi_window")) or DEFAULT_RSI_WINDOW,
        bb_window=DEFAULT_BB_WINDOW,
        bb_alpha=DEFAULT_BB_ALPHA,
        atr_window=DEFAULT_ATR_WINDOW,
        ma_pairs=ma_pairs,
        obv_lookbacks=_lookback_values("obv_lookback", "obv_roc"),
        oi_lookbacks=_lookback_values("oi_lookback", "oi_roc"),
        open_interest_provider=str(runtime_settings.get("open_interest_provider") or "bybit"),
        volume_lookbacks=_lookback_values("volume_lookback", "volume_z"),
        roc_lookbacks=_lookback_values("roc_lookback", "roc"),
        cmf_lookbacks=_lookback_values("cmf_lookback", "cmf"),
        mfi_window=DEFAULT_MFI_WINDOW,
        vroc_lookbacks=_lookback_values("vroc_lookback", "vroc"),
        ad_lookbacks=_lookback_values("ad_lookback", "ad"),
        cci_lookbacks=_lookback_values("cci_lookback", "cci"),
        willr_lookbacks=_lookback_values("willr_lookback", "willr"),
        adx_lookbacks=_lookback_values("adx_lookback", "adx"),
        trix_lookbacks=_lookback_values("trix_lookback", "trix"),
        dpo_lookbacks=_lookback_values("dpo_lookback", "dpo"),
        efi_lookbacks=_lookback_values("efi_lookback", "efi"),
        vwma_lookbacks=_lookback_values("vwma_lookback", "vwma_trend"),
        ultosc_periods=DEFAULT_ULTOSC_PERIODS,
        keltner_lookbacks=_lookback_values("keltner_lookback", "keltner_pos"),
        donchian_lookbacks=_lookback_values("donchian_lookback", "donchian_pos"),
        ppo_fast=DEFAULT_PPO_FAST,
        ppo_slow=DEFAULT_PPO_SLOW,
        ppo_signal=DEFAULT_PPO_SIGNAL,
        chop_lookbacks=_lookback_values("chop_lookback", "chop"),
        init_cash_usdt=float(runtime_settings.get("init_cash_usdt") or 1000.0),
        capital_mode=str(runtime_settings.get("capital_mode") or "shared"),
        htf_trend_timeframes=overlay_requirements["htf_trend_timeframes"],
        htf_trend_windows=overlay_requirements["htf_trend_windows"],
        funding_gate_long_thresholds=overlay_requirements["funding_gate_long_thresholds"],
        funding_gate_short_thresholds=overlay_requirements["funding_gate_short_thresholds"],
    )

    regime_variants = engine_helpers._build_regime_variants(
        DEFAULT_RSI_REVERT_PAIRS,
        preset=runtime_settings.get("regime_preset", "full"),
        regime_name_filter=[selected_row.get("regime_name")],
    )
    if not regime_variants:
        raise ValueError(f"regime not found for selected row: {selected_row.get('regime_name')}")

    return {
        "metadata": metadata,
        "default_config": default_config,
        "runtime_settings": runtime_settings,
        "timeframe_config": timeframe_config,
        "filter_spec": filter_spec,
        "combo_params": combo_params,
        "ctx": ctx,
        "bar_hours": bar_hours,
        "combo_indicator_keys": combo_indicator_keys,
        "state_indicator_combo": state_indicator_combo,
        "trigger_indicator_combo": trigger_indicator_combo,
        "regime": regime_variants[0],
        "vol_lookback": vol_lookback,
        "vol_z": _safe_float(selected_row.get("vol_z")) or 0.8,
        "mom_lookback": mom_lookback,
        "trade_mom_lookback": trade_mom_lookback,
        "rsi_window": _safe_int(selected_row.get("rsi_window")) or DEFAULT_RSI_WINDOW,
    }


def _build_executable_signal_matrices(
    *,
    trade_close: pd.DataFrame,
    long_entries_raw: pd.DataFrame | pd.Series,
    short_entries_raw: pd.DataFrame | pd.Series,
    long_exits_raw: pd.DataFrame | pd.Series | None,
    short_exits_raw: pd.DataFrame | pd.Series | None,
    long_filter: pd.DataFrame,
    short_filter: pd.DataFrame,
    trade_mom: pd.DataFrame,
    max_hold: int,
    capital_mode: str,
    max_concurrent_positions: int,
) -> dict[str, pd.DataFrame]:
    long_signal = autowfo_portfolio._to_signal_matrix(long_entries_raw, trade_close)
    short_signal = autowfo_portfolio._to_signal_matrix(short_entries_raw, trade_close)
    long_signal = long_signal & long_filter.fillna(False)
    short_signal = short_signal & short_filter.fillna(False)
    enter_long = long_signal.vbt.fshift(1, fill_value=False)
    enter_short = short_signal.vbt.fshift(1, fill_value=False)
    if capital_mode == "shared" and max_concurrent_positions > 0:
        long_scores = trade_mom.reindex_like(enter_long).where(enter_long, -np.inf).fillna(-np.inf)
        long_ranks = long_scores.rank(axis=1, method="first", ascending=False)
        enter_long = enter_long & (long_ranks <= max_concurrent_positions)
        short_scores = trade_mom.reindex_like(enter_short).where(enter_short, -np.inf).fillna(-np.inf)
        short_ranks = short_scores.rank(axis=1, method="first", ascending=False)
        enter_short = enter_short & (short_ranks <= max_concurrent_positions)
    exit_long = enter_long.vbt.fshift(int(max_hold), fill_value=False)
    exit_short = enter_short.vbt.fshift(int(max_hold), fill_value=False)
    explicit_exit_long = autowfo_portfolio._to_signal_matrix(long_exits_raw, trade_close)
    explicit_exit_short = autowfo_portfolio._to_signal_matrix(short_exits_raw, trade_close)
    if explicit_exit_long is not None:
        exit_long = exit_long | explicit_exit_long.vbt.fshift(1, fill_value=False)
    if explicit_exit_short is not None:
        exit_short = exit_short | explicit_exit_short.vbt.fshift(1, fill_value=False)
    return {
        "signal_long": long_signal,
        "signal_short": short_signal,
        "enter_long": enter_long,
        "enter_short": enter_short,
        "exit_long": exit_long,
        "exit_short": exit_short,
        "explicit_exit_long": explicit_exit_long if explicit_exit_long is not None else enter_long & False,
        "explicit_exit_short": explicit_exit_short if explicit_exit_short is not None else enter_short & False,
    }


def _portfolio_summary(*, pf: Any, trade_symbols: Sequence[str], bar_hours: float, capital_mode: str) -> dict[str, Any]:
    series_metrics = autowfo_metrics._calc_pf_series(pf, list(trade_symbols), bar_hours)
    symbol_metrics = autowfo_metrics._aggregate_metrics(series_metrics)
    if str(capital_mode or "shared") == "shared":
        combo_metrics = autowfo_metrics._calc_pf_combo_metrics(pf, bar_hours)
    else:
        combo_metrics = {
            "total_return_pct": symbol_metrics["avg_total_return_pct"],
            "total_profit": np.nan,
            "total_trades": symbol_metrics["avg_total_trades"],
            "win_rate_pct": symbol_metrics["avg_win_rate_pct"],
            "avg_trade_pct": symbol_metrics["avg_avg_trade_pct"],
            "max_drawdown_pct": symbol_metrics["avg_max_drawdown_pct"],
            "position_coverage_pct": symbol_metrics["avg_position_coverage_pct"],
            "avg_hold_hours": symbol_metrics["avg_hold_hours"],
        }
    trade_count = int(len(pf.trades.records))
    return {
        "total_return_pct": _safe_float(combo_metrics.get("total_return_pct")),
        "total_trades": _safe_float(combo_metrics.get("total_trades")),
        "win_rate_pct": _safe_float(combo_metrics.get("win_rate_pct")),
        "avg_trade_pct": _safe_float(combo_metrics.get("avg_trade_pct")),
        "max_drawdown_pct": _safe_float(combo_metrics.get("max_drawdown_pct")),
        "position_coverage_pct": _safe_float(combo_metrics.get("position_coverage_pct")),
        "avg_hold_hours": _safe_float(combo_metrics.get("avg_hold_hours")),
        "trade_count": trade_count,
        "long_trade_count": int((pf.trades.records_readable.get("Direction") == "Long").sum()),
        "short_trade_count": int((pf.trades.records_readable.get("Direction") == "Short").sum()),
        "pair_count": len(list(trade_symbols)),
    }


def _portfolio_trades_frame(pf: Any) -> pd.DataFrame:
    readable = pf.trades.records_readable.copy()
    if readable.empty:
        return pd.DataFrame(
            columns=[
                "pair",
                "entry_timestamp",
                "exit_timestamp",
                "direction",
                "return_ratio",
                "return_pct",
                "pnl",
                "status",
            ]
        )
    trades = pd.DataFrame(
        {
            "pair": readable["Column"].astype(str),
            "entry_timestamp": readable["Entry Timestamp"].apply(_normalize_timestamp_value),
            "exit_timestamp": readable["Exit Timestamp"].apply(_normalize_timestamp_value),
            "direction": readable["Direction"].astype(str),
            "return_ratio": pd.to_numeric(readable["Return"], errors="coerce"),
            "pnl": pd.to_numeric(readable["PnL"], errors="coerce"),
            "status": readable["Status"].astype(str),
        }
    )
    trades["return_pct"] = trades["return_ratio"] * 100.0
    return trades


def reconstruct_frozen_lane(
    main_run: Mapping[str, Any],
    *,
    selected_row: Mapping[str, Any],
    cwd: str | Path | None = None,
    rolling_window: bool = False,
) -> dict[str, Any]:
    resolved = _resolve_runtime_context(
        main_run,
        selected_row=selected_row,
        cwd=cwd,
        rolling_window=rolling_window,
    )
    ctx = resolved["ctx"]
    runtime_settings = resolved["runtime_settings"]
    regime = resolved["regime"]
    filter_spec = resolved["filter_spec"]
    combo_params = dict(resolved["combo_params"])
    trade_close = ctx["trade_close"]
    trade_mom = ctx["trade_mom_by_lb"][resolved["trade_mom_lookback"]]
    vol_cond_source = ctx["vol_zscore_by_lb"][resolved["vol_lookback"]]

    if regime["vol_mode"] == "high":
        vol_cond = vol_cond_source > float(resolved["vol_z"])
    elif regime["vol_mode"] == "low":
        vol_cond = vol_cond_source < -float(resolved["vol_z"])
    else:
        vol_cond = pd.Series(True, index=vol_cond_source.index)

    long_regime, short_regime, regime_rsi_long, regime_rsi_short = engine_runtime._resolve_regime_signals(
        regime=regime,
        vol_cond=vol_cond,
        ctx=ctx,
        mom_lookback=resolved["mom_lookback"],
    )
    base_long_filter, base_short_filter = engine_runtime._build_trade_mom_filters(trade_mom)
    overlay_long_filter, overlay_short_filter = engine_runtime._build_overlay_filters(ctx, filter_spec, trade_mom)
    long_filter = base_long_filter & overlay_long_filter
    short_filter = base_short_filter & overlay_short_filter
    effective_fees, effective_slippage = engine_runtime._compute_effective_costs(
        float(DEFAULT_FEES),
        float(runtime_settings.get("slippage_bps") or 0.0),
        float(runtime_settings.get("spread_bps") or 0.0),
        float(runtime_settings.get("funding_rate_daily") or 0.0),
        int(selected_row.get("max_hold") or 1),
        resolved["bar_hours"],
    )
    strategy_signals = autowfo_evaluator._build_strategy_mode_signals(
        strategy_mode=str(selected_row.get("strategy_mode") or runtime_settings.get("strategy_mode") or "combo_entry"),
        state_exit_policy=selected_row.get("state_exit_policy") or runtime_settings.get("state_exit_policy"),
        long_regime=long_regime,
        short_regime=short_regime,
        indicator_combo=resolved["combo_indicator_keys"],
        state_indicator_combo=resolved["state_indicator_combo"],
        trigger_indicator_combo=resolved["trigger_indicator_combo"],
        combo_params=combo_params,
        ctx=ctx,
    )
    pf_sl_stop, pf_tp_stop = autowfo_evaluator._resolve_pf_stops(
        ctx=ctx,
        risk_mode=str(runtime_settings.get("risk_mode") or "fixed_pct"),
        sl_stop=selected_row.get("sl_stop"),
        tp_stop=selected_row.get("tp_stop"),
    )
    pf = autowfo_portfolio._run_pf(
        trade_close,
        strategy_signals["long_entries"],
        strategy_signals["short_entries"],
        int(selected_row.get("max_hold") or 1),
        effective_fees,
        pf_sl_stop,
        pf_tp_stop,
        freq=str(resolved["timeframe_config"].get("timeframe") or selected_row.get("timeframe") or "2h"),
        slippage=effective_slippage,
        long_exits=strategy_signals["long_exits"],
        short_exits=strategy_signals["short_exits"],
        long_filter=long_filter,
        short_filter=short_filter,
        init_cash=ctx["init_cash_btc"],
        size=float(runtime_settings.get("order_size_pct") or 0.5),
        size_type="percent",
        cash_sharing=(str(runtime_settings.get("capital_mode") or "shared") == "shared"),
        lock_cash=True,
        allow_partial=False,
        max_positions=(
            int(runtime_settings.get("max_concurrent_positions") or 0)
            if str(runtime_settings.get("capital_mode") or "shared") == "shared"
            else None
        ),
        long_scores=trade_mom,
        short_scores=-trade_mom,
    )
    signal_matrices = _build_executable_signal_matrices(
        trade_close=trade_close,
        long_entries_raw=strategy_signals["long_entries"],
        short_entries_raw=strategy_signals["short_entries"],
        long_exits_raw=strategy_signals["long_exits"],
        short_exits_raw=strategy_signals["short_exits"],
        long_filter=long_filter,
        short_filter=short_filter,
        trade_mom=trade_mom,
        max_hold=int(selected_row.get("max_hold") or 1),
        capital_mode=str(runtime_settings.get("capital_mode") or "shared"),
        max_concurrent_positions=int(runtime_settings.get("max_concurrent_positions") or 0),
    )

    signal_frames = []
    for pair in trade_close.columns:
        pair_frame = pd.DataFrame(
            {
                "date": trade_close.index,
                "pair": pair,
                "close": pd.to_numeric(trade_close[pair], errors="coerce"),
                **{
                    column: signal_matrices[column][pair].fillna(False).astype(int)
                    for column in DEFAULT_SIGNAL_COLUMNS
                },
            }
        )
        signal_frames.append(pair_frame)
    signal_df = pd.concat(signal_frames, ignore_index=True)
    validate_signal_store_frame(signal_df)

    trade_df = _portfolio_trades_frame(pf)
    summary = _portfolio_summary(
        pf=pf,
        trade_symbols=list(ctx.get("trade_symbols") or trade_close.columns),
        bar_hours=resolved["bar_hours"],
        capital_mode=str(runtime_settings.get("capital_mode") or "shared"),
    )
    summary["regime_rsi_long"] = regime_rsi_long
    summary["regime_rsi_short"] = regime_rsi_short
    summary["init_cash_btc"] = _safe_float(ctx.get("init_cash_btc"))
    return {
        "resolved": resolved,
        "signal_df": signal_df,
        "trade_df": trade_df,
        "summary": summary,
        "has_short_signals": bool(int(signal_df["enter_short"].sum()) > 0 or int(signal_df["signal_short"].sum()) > 0),
    }


def export_signal_bundle(
    analysis_payload: Mapping[str, Any],
    main_run: Mapping[str, Any],
    *,
    selection: str = "canonical",
    rank: int = 1,
    out_dir: str | Path,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    if not autowfo_data._has_parquet_engine():
        raise RuntimeError("signal bundle export requires pyarrow or fastparquet in the AUTOWFO environment")

    selected_row = select_analysis_candidate(analysis_payload, selection=selection, rank=rank)
    reconstructed = reconstruct_frozen_lane(main_run, selected_row=selected_row, cwd=cwd)
    resolved = reconstructed["resolved"]
    signal_df = reconstructed["signal_df"]
    trade_df = reconstructed["trade_df"]

    output_dir = Path(out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_parquet_path = output_dir / "signals.parquet"
    signal_csv_path = output_dir / "signals.csv"
    autowfo_trades_path = output_dir / "autowfo_trades.csv"
    manifest_path = output_dir / "signal_manifest.json"

    signal_df.to_parquet(signal_parquet_path, index=False)
    signal_df.to_csv(signal_csv_path, index=False)
    trade_df.to_csv(autowfo_trades_path, index=False)

    metadata = dict(main_run.get("metadata") or {})
    base_config, base_config_path = _load_base_config(main_run, cwd=cwd)
    pairs = sorted(signal_df["pair"].dropna().astype(str).unique().tolist())
    quote_currency = ""
    if pairs and "/" in pairs[0]:
        quote_currency = pairs[0].split("/")[-1]
    manifest = {
        "schema_version": SIGNAL_BUNDLE_MANIFEST_VERSION,
        "signal_store_schema_version": SIGNAL_STORE_SCHEMA_VERSION,
        "created_utc": _utc_now_iso(),
        "analysis": {
            "selection": selected_row.get("analysis_bucket"),
            "rank": selected_row.get("analysis_rank"),
            "main_run_id": metadata.get("run_id") or main_run.get("run_id"),
            "selected_row": dict(selected_row),
        },
        "source": {
            "run_root": str(main_run.get("run_root")),
            "config_path": str(base_config_path) if base_config_path is not None else None,
            "exchange": metadata.get("exchange") or base_config.get("exchange") or "binance",
            "base_symbol": metadata.get("base_symbol") or base_config.get("base_symbol") or "BTC/USDT",
            "quote_currency": quote_currency,
            "timeframe": selected_row.get("timeframe"),
            "data_days": selected_row.get("data_days"),
            "pair_count": len(pairs),
            "pairs": pairs,
            "data_start": _normalize_timestamp_value(signal_df["date"].min()),
            "data_end": _normalize_timestamp_value(signal_df["date"].max()),
        },
        "replay_contract": {
            "strategy_mode": selected_row.get("strategy_mode") or resolved["runtime_settings"].get("strategy_mode"),
            "state_exit_policy": selected_row.get("state_exit_policy") or resolved["runtime_settings"].get("state_exit_policy"),
            "risk_mode": resolved["runtime_settings"].get("risk_mode"),
            "capital_mode": resolved["runtime_settings"].get("capital_mode"),
            "pilot_fixed_indicator_params": _safe_bool(resolved["runtime_settings"].get("pilot_fixed_indicator_params")),
            "open_interest_provider": resolved["runtime_settings"].get("open_interest_provider"),
        },
        "signals": {
            "primary_format": "parquet",
            "path": str(signal_parquet_path),
            "csv_path": str(signal_csv_path),
            "rows": int(len(signal_df)),
            "columns": list(signal_df.columns),
            "has_short_signals": bool(reconstructed["has_short_signals"]),
            "enter_long_count": int(signal_df["enter_long"].sum()),
            "enter_short_count": int(signal_df["enter_short"].sum()),
            "exit_long_count": int(signal_df["exit_long"].sum()),
            "exit_short_count": int(signal_df["exit_short"].sum()),
        },
        "autowfo_replay": {
            "summary": reconstructed["summary"],
            "trades_path": str(autowfo_trades_path),
        },
        "freqtrade": {
            "strategy_path": str((Path(__file__).resolve().parents[1] / "scripts" / "freqtrade_generic_signal_strategy.py")),
            "recommended_strategy": (
                "AutowfoGenericSignalStrategyLongShort"
                if reconstructed["has_short_signals"]
                else "AutowfoGenericSignalStrategyLongOnly"
            ),
            "recommended_trading_mode": "futures" if reconstructed["has_short_signals"] else "spot",
            "autowfo_pair_mapping": _default_execution_pair_mapping(
                pairs,
                trading_mode=("futures" if reconstructed["has_short_signals"] else "spot"),
            ),
        },
    }
    validate_signal_bundle_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_signal_bundle_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("signal bundle manifest must decode to an object")
    validate_signal_bundle_manifest(payload)
    return payload


def build_freqtrade_backtest_config(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path,
    datadir: str | Path,
    strategy_name: str | None = None,
    trading_mode: str | None = None,
) -> dict[str, Any]:
    source = dict(manifest.get("source") or {})
    signals = dict(manifest.get("signals") or {})
    freqtrade = dict(manifest.get("freqtrade") or {})
    resolved_datadir = Path(datadir).resolve()
    user_data_dir = resolved_datadir
    for candidate in [resolved_datadir, *resolved_datadir.parents]:
        if candidate.name == "user_data":
            user_data_dir = candidate
            break
    source_pairs = list(source.get("pairs") or [])
    resolved_strategy = str(strategy_name or freqtrade.get("recommended_strategy") or "AutowfoGenericSignalStrategyLongOnly")
    requires_short = _safe_bool(signals.get("has_short_signals"))
    resolved_trading_mode = str(trading_mode or freqtrade.get("recommended_trading_mode") or ("futures" if requires_short else "spot"))
    if requires_short and resolved_trading_mode == "spot":
        raise ValueError("selected signal bundle contains short signals and requires trading_mode=futures")
    pair_mapping = _resolve_pair_mapping(manifest, trading_mode=resolved_trading_mode)
    execution_pairs = _resolve_execution_pairs(source_pairs, pair_mapping)
    stake_currency = _resolve_execution_quote_currency(execution_pairs, str(source.get("quote_currency") or "USDT"))
    exchange_payload = {
        "name": str(source.get("exchange") or "binance"),
        "pair_whitelist": execution_pairs,
        "pair_blacklist": [],
        "ccxt_config": {},
        "ccxt_async_config": {},
    }
    if resolved_trading_mode == "futures":
        exchange_payload["ccxt_config"] = {"options": {"defaultType": "future"}}
        exchange_payload["ccxt_async_config"] = {"options": {"defaultType": "future"}}
    config = {
        "strategy": resolved_strategy,
        "timeframe": str(source.get("timeframe") or "2h"),
        "stake_currency": stake_currency,
        "stake_amount": 100.0,
        "dry_run_wallet": 1000.0,
        "max_open_trades": max(len(execution_pairs), 1),
        "trading_mode": resolved_trading_mode,
        "margin_mode": "isolated" if resolved_trading_mode == "futures" else "",
        "exchange": exchange_payload,
        "entry_pricing": {
            "price_side": "same",
            "use_order_book": True,
            "order_book_top": 1,
        },
        "exit_pricing": {
            "price_side": "same",
            "use_order_book": True,
            "order_book_top": 1,
        },
        "pairlists": [{"method": "StaticPairList"}],
        "datadir": str(resolved_datadir),
        "user_data_dir": str(user_data_dir),
        "dataformat_ohlcv": "json",
        "dataformat_trades": "json",
        "autowfo_signal_manifest": str(Path(manifest_path).resolve()),
    }
    if pair_mapping:
        config["autowfo_pair_mapping"] = dict(pair_mapping)
    return config


def build_freqtrade_backtest_command(
    *,
    freqtrade_exe: str | Path,
    config_path: str | Path,
    strategy_name: str,
    strategy_path: str | Path,
    datadir: str | Path,
    backtest_directory: str | Path,
    fee: float | None = None,
) -> list[str]:
    resolved_strategy_path = Path(strategy_path).resolve()
    if resolved_strategy_path.is_file():
        resolved_strategy_path = resolved_strategy_path.parent
    command = [
        str(freqtrade_exe),
        "backtesting",
        "--config",
        str(Path(config_path).resolve()),
        "--strategy",
        str(strategy_name),
        "--strategy-path",
        str(resolved_strategy_path),
        "--datadir",
        str(Path(datadir).resolve()),
        "--export",
        "trades",
        "--backtest-directory",
        str(Path(backtest_directory).resolve()),
        "--cache",
        "none",
    ]
    if fee is not None:
        command.extend(["--fee", f"{float(fee):.10f}"])
    return command


def load_freqtrade_backtest_result(
    path: str | Path,
    *,
    strategy_name: str | None = None,
) -> dict[str, Any]:
    resolved_path = Path(path).resolve()
    if resolved_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(resolved_path) as archive:
            json_members = [member for member in archive.namelist() if member.lower().endswith(".json")]
            payload = None
            for member in json_members:
                if member.lower().endswith("_config.json"):
                    continue
                with archive.open(member) as handle:
                    candidate = json.loads(handle.read().decode("utf-8-sig"))
                if isinstance(candidate, dict) and isinstance(candidate.get("strategy"), Mapping):
                    payload = candidate
                    break
            if payload is None:
                raise ValueError(f"Freqtrade backtest zip has no strategy payload JSON: {resolved_path}")
    else:
        payload = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Freqtrade backtest result must decode to an object")
    strategy_payloads = payload.get("strategy")
    if not isinstance(strategy_payloads, Mapping) or not strategy_payloads:
        raise ValueError("Freqtrade backtest result has no strategy payload")
    resolved_strategy = str(strategy_name or next(iter(strategy_payloads.keys())))
    if resolved_strategy not in strategy_payloads:
        raise ValueError(f"strategy '{resolved_strategy}' not found in Freqtrade backtest result")
    selected_payload = dict(strategy_payloads[resolved_strategy] or {})
    trades_df = pd.DataFrame(selected_payload.get("trades") or [])
    if trades_df.empty:
        normalized_trades = pd.DataFrame(
            columns=["pair", "entry_timestamp", "exit_timestamp", "direction", "profit_ratio", "exit_reason"]
        )
    else:
        is_short = trades_df["is_short"] if "is_short" in trades_df.columns else pd.Series(False, index=trades_df.index)
        normalized_trades = pd.DataFrame(
            {
                "pair": trades_df.get("pair", pd.Series(dtype=str)).astype(str),
                "entry_timestamp": _normalize_timestamp_series(trades_df.get("open_date", pd.Series(dtype=object))).apply(
                    lambda value: value.isoformat() if pd.notna(value) else None
                ),
                "exit_timestamp": _normalize_timestamp_series(trades_df.get("close_date", pd.Series(dtype=object))).apply(
                    lambda value: value.isoformat() if pd.notna(value) else None
                ),
                "direction": np.where(is_short.fillna(False), "Short", "Long"),
                "profit_ratio": pd.to_numeric(trades_df.get("profit_ratio"), errors="coerce"),
                "exit_reason": trades_df.get("exit_reason", pd.Series(dtype=str)).astype(str),
            }
        )
    summary = {key: value for key, value in selected_payload.items() if key != "trades"}
    return {
        "strategy_name": resolved_strategy,
        "summary": summary,
        "trades_df": normalized_trades,
    }


def compare_trade_sets(autowfo_trades: pd.DataFrame, freqtrade_trades: pd.DataFrame) -> dict[str, Any]:
    left = autowfo_trades.copy()
    right = freqtrade_trades.copy()
    for frame in (left, right):
        for column in ("pair", "direction", "entry_timestamp", "exit_timestamp"):
            if column not in frame.columns:
                frame[column] = None
            frame[column] = frame[column].astype(str)
    left["exact_key"] = (
        left["pair"] + "|" + left["direction"] + "|" + left["entry_timestamp"] + "|" + left["exit_timestamp"]
    )
    right["exact_key"] = (
        right["pair"] + "|" + right["direction"] + "|" + right["entry_timestamp"] + "|" + right["exit_timestamp"]
    )
    left["open_key"] = left["pair"] + "|" + left["direction"] + "|" + left["entry_timestamp"]
    right["open_key"] = right["pair"] + "|" + right["direction"] + "|" + right["entry_timestamp"]

    exact_match_keys = sorted(set(left["exact_key"]) & set(right["exact_key"]))
    open_match_keys = sorted(set(left["open_key"]) & set(right["open_key"]))
    per_pair = (
        left.groupby(["pair", "direction"]).size().rename("autowfo_count").reset_index()
        .merge(
            right.groupby(["pair", "direction"]).size().rename("freqtrade_count").reset_index(),
            on=["pair", "direction"],
            how="outer",
        )
        .fillna(0)
    )
    per_pair["autowfo_count"] = per_pair["autowfo_count"].astype(int)
    per_pair["freqtrade_count"] = per_pair["freqtrade_count"].astype(int)
    per_pair["delta"] = per_pair["freqtrade_count"] - per_pair["autowfo_count"]

    exact_left = left[left["exact_key"].isin(exact_match_keys)][["exact_key", "return_ratio"]].rename(
        columns={"return_ratio": "autowfo_return_ratio"}
    )
    exact_right = right[right["exact_key"].isin(exact_match_keys)][["exact_key", "profit_ratio"]].rename(
        columns={"profit_ratio": "freqtrade_profit_ratio"}
    )
    exact_merged = exact_left.merge(exact_right, on="exact_key", how="inner")
    profit_ratio_abs_delta_mean = None
    if not exact_merged.empty:
        profit_ratio_abs_delta_mean = float(
            (exact_merged["autowfo_return_ratio"] - exact_merged["freqtrade_profit_ratio"]).abs().mean()
        )

    exact_match_ratio = float(len(exact_match_keys) / max(len(left), 1))
    open_match_ratio = float(len(open_match_keys) / max(len(left), 1))
    verdict = "passed"
    if len(left) != len(right) or len(exact_match_keys) != len(left):
        verdict = "review"
    return {
        "verdict": verdict,
        "autowfo_trade_count": int(len(left)),
        "freqtrade_trade_count": int(len(right)),
        "trade_count_delta": int(len(right) - len(left)),
        "exact_match_count": int(len(exact_match_keys)),
        "open_match_count": int(len(open_match_keys)),
        "exact_match_ratio": exact_match_ratio,
        "open_match_ratio": open_match_ratio,
        "profit_ratio_abs_delta_mean": profit_ratio_abs_delta_mean,
        "per_pair_counts": per_pair.to_dict(orient="records"),
    }


def build_parity_report(
    manifest: Mapping[str, Any],
    *,
    freqtrade_result: Mapping[str, Any],
) -> dict[str, Any]:
    autowfo_trades_path = Path((manifest.get("autowfo_replay") or {}).get("trades_path") or "")
    autowfo_trades = pd.read_csv(autowfo_trades_path) if autowfo_trades_path.exists() else pd.DataFrame()
    freqtrade_trades_raw = freqtrade_result.get("trades_df")
    if isinstance(freqtrade_trades_raw, pd.DataFrame):
        freqtrade_trades = freqtrade_trades_raw.copy()
    else:
        freqtrade_trades = pd.DataFrame(freqtrade_trades_raw or pd.DataFrame())
    pair_mapping = _resolve_pair_mapping(
        manifest,
        trading_mode=str((manifest.get("freqtrade") or {}).get("recommended_trading_mode") or "spot"),
    )
    freqtrade_trades = _normalize_trade_pairs(freqtrade_trades, pair_mapping)
    trade_comparison = compare_trade_sets(autowfo_trades, freqtrade_trades)
    report = {
        "schema_version": SIGNAL_BUNDLE_MANIFEST_VERSION,
        "created_utc": _utc_now_iso(),
        "analysis": dict(manifest.get("analysis") or {}),
        "source": dict(manifest.get("source") or {}),
        "autowfo_replay": dict((manifest.get("autowfo_replay") or {}).get("summary") or {}),
        "freqtrade": {
            "strategy_name": freqtrade_result.get("strategy_name"),
            "summary": dict(freqtrade_result.get("summary") or {}),
            "autowfo_pair_mapping": dict(pair_mapping),
        },
        "trade_comparison": trade_comparison,
    }
    return report


def run_freqtrade_cross_check(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path,
    out_dir: str | Path,
    datadir: str | Path | None,
    freqtrade_exe: str | Path | None = None,
    strategy_name: str | None = None,
    trading_mode: str | None = None,
    execute: bool = True,
) -> dict[str, Any]:
    output_dir = Path(out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    strategy_path = Path((manifest.get("freqtrade") or {}).get("strategy_path") or "scripts/freqtrade_generic_signal_strategy.py")
    config_path = output_dir / "freqtrade_backtest_config.json"
    report_path = output_dir / "parity_report.json"

    if datadir is None and execute:
        raise ValueError("datadir is required when execute=true")
    resolved_datadir = Path(datadir).resolve() if datadir is not None else output_dir
    config_payload = build_freqtrade_backtest_config(
        manifest,
        manifest_path=manifest_path,
        datadir=resolved_datadir,
        strategy_name=strategy_name,
        trading_mode=trading_mode,
    )
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    resolved_strategy_name = str(config_payload.get("strategy") or strategy_name or "AutowfoGenericSignalStrategyLongOnly")
    command = build_freqtrade_backtest_command(
        freqtrade_exe=freqtrade_exe or "freqtrade",
        config_path=config_path,
        strategy_name=resolved_strategy_name,
        strategy_path=strategy_path,
        datadir=resolved_datadir,
        backtest_directory=output_dir,
        fee=_safe_float(DEFAULT_FEES),
    )
    payload: dict[str, Any] = {
        "config_path": str(config_path),
        "strategy_name": resolved_strategy_name,
        "strategy_path": str(strategy_path.resolve()),
        "backtest_directory": str(output_dir),
        "command": command,
        "executed": False,
        "parity_report_path": str(report_path),
    }
    if not execute:
        return payload
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    payload["executed"] = True
    payload["returncode"] = int(completed.returncode)
    payload["stdout_tail"] = completed.stdout[-4000:]
    payload["stderr_tail"] = completed.stderr[-4000:]
    if completed.returncode != 0:
        raise RuntimeError(
            "Freqtrade backtesting failed with exit code "
            f"{completed.returncode}: {completed.stderr[-1000:]}"
        )
    result_path = _resolve_backtest_result_path(output_dir)
    payload["result_path"] = str(result_path)
    freqtrade_result = load_freqtrade_backtest_result(result_path, strategy_name=resolved_strategy_name)
    parity_report = build_parity_report(manifest, freqtrade_result=freqtrade_result)
    report_path.write_text(json.dumps(parity_report, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["parity_report"] = parity_report
    return payload