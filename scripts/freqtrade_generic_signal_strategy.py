"""Manifest-driven Freqtrade strategy shells for AUTOWFO signal bundles."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
from pandas import DataFrame


class IStrategy:
    pass


try:  # pragma: no cover - resolves when the file is loaded by Freqtrade itself
    IStrategy = importlib.import_module("freqtrade.strategy").IStrategy
except Exception:
    pass


SIGNAL_COLUMNS = (
    "signal_long",
    "signal_short",
    "enter_long",
    "enter_short",
    "exit_long",
    "exit_short",
    "explicit_exit_long",
    "explicit_exit_short",
)

FT_SIGNAL_COLUMNS = (
    "ft_enter_long",
    "ft_enter_short",
    "ft_exit_long",
    "ft_exit_short",
)


def _resolve_manifest_path(config: dict[str, Any]) -> Path:
    raw_path = config.get("autowfo_signal_manifest") or os.environ.get("AUTOWFO_SIGNAL_MANIFEST")
    if not raw_path:
        raise ValueError("autowfo_signal_manifest is required in the Freqtrade config")
    manifest_path = Path(str(raw_path)).resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"AUTOWFO signal manifest not found: {manifest_path}")
    return manifest_path


def _load_signal_bundle(manifest_path: Path) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise ValueError("AUTOWFO signal manifest must decode to an object")

    signals = dict(manifest.get("signals") or {})
    signal_path = Path(str(signals.get("path") or "")).resolve() if signals.get("path") else None
    csv_path = Path(str(signals.get("csv_path") or "")).resolve() if signals.get("csv_path") else None
    signal_df: pd.DataFrame | None = None
    if signal_path is not None and signal_path.exists():
        try:
            signal_df = pd.read_parquet(signal_path)
        except Exception:
            signal_df = None
    if signal_df is None:
        if csv_path is None or not csv_path.exists():
            raise FileNotFoundError(
                "AUTOWFO signal store could not be loaded; missing readable parquet and csv fallback"
            )
        signal_df = pd.read_csv(csv_path)
    if signal_df.empty:
        return manifest, {}

    signal_df = signal_df.copy()
    signal_df["date"] = pd.to_datetime(signal_df["date"], utc=True, errors="coerce")
    signal_frames: dict[str, pd.DataFrame] = {}
    for pair, pair_df in signal_df.groupby("pair", sort=False):
        ordered = pair_df.drop(columns=["pair"]).sort_values("date").reset_index(drop=True)
        ordered = _prepare_pair_signals_for_freqtrade(ordered)
        signal_frames[str(pair)] = ordered
    return manifest, signal_frames


def _empty_signal_columns(dataframe: DataFrame) -> DataFrame:
    result = dataframe.copy()
    for column in (*SIGNAL_COLUMNS, *FT_SIGNAL_COLUMNS):
        result[column] = 0
    return result


def _prepare_pair_signals_for_freqtrade(pair_signals: pd.DataFrame) -> pd.DataFrame:
    prepared = pair_signals.copy()
    for column in SIGNAL_COLUMNS:
        prepared[column] = prepared.get(column, 0).fillna(0).astype(int)
    prepared["ft_enter_long"] = prepared["signal_long"]
    prepared["ft_enter_short"] = prepared["signal_short"]
    # FT interprets entry/exit flags as "signal observed on this bar, execute next bar open".
    prepared["ft_exit_long"] = prepared["exit_long"].shift(-1, fill_value=0).astype(int)
    prepared["ft_exit_short"] = prepared["exit_short"].shift(-1, fill_value=0).astype(int)
    return prepared


def _merge_pair_signals(dataframe: DataFrame, pair_signals: pd.DataFrame | None) -> DataFrame:
    result = dataframe.copy()
    result["date"] = pd.to_datetime(result["date"], utc=True, errors="coerce")
    if pair_signals is None or pair_signals.empty:
        return _empty_signal_columns(result)
    signal_columns = ["date", *SIGNAL_COLUMNS, *FT_SIGNAL_COLUMNS]
    filtered_pair_signals = pair_signals[[column for column in signal_columns if column in pair_signals.columns]].copy()
    merged = result.merge(filtered_pair_signals, on="date", how="left")
    for column in (*SIGNAL_COLUMNS, *FT_SIGNAL_COLUMNS):
        merged[column] = merged.get(column, 0).fillna(0).astype(int)
    return merged


def _resolve_pair_mapping(config: dict[str, Any]) -> dict[str, str]:
    raw_mapping = config.get("autowfo_pair_mapping") or {}
    if not isinstance(raw_mapping, dict):
        return {}
    return {
        str(source).strip(): str(target).strip()
        for source, target in raw_mapping.items()
        if str(source).strip() and str(target).strip()
    }


def _resolve_source_pair(
    pair: str,
    *,
    config: dict[str, Any],
    signal_frames: dict[str, pd.DataFrame],
) -> str:
    if pair in signal_frames:
        return pair
    reverse_mapping = {target: source for source, target in _resolve_pair_mapping(config).items()}
    return reverse_mapping.get(pair, pair)


def _coerce_timestamp(raw_value: Any) -> pd.Timestamp | None:
    ts = pd.to_datetime(raw_value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def _timeframe_to_timedelta(timeframe: Any) -> pd.Timedelta:
    text = str(timeframe or "2h").strip().lower()
    if len(text) < 2:
        return pd.Timedelta(hours=2)
    try:
        amount = float(text[:-1])
    except Exception:
        return pd.Timedelta(hours=2)
    unit = text[-1]
    if unit == "m":
        return pd.Timedelta(minutes=amount)
    if unit == "h":
        return pd.Timedelta(hours=amount)
    if unit == "d":
        return pd.Timedelta(days=amount)
    if unit == "w":
        return pd.Timedelta(weeks=amount)
    return pd.Timedelta(hours=2)


def _manifest_is_stale(
    manifest: dict[str, Any],
    config: dict[str, Any],
    *,
    reference_ts: pd.Timestamp | None = None,
) -> bool:
    runtime_payload = dict(manifest.get("runtime") or {})
    signals_payload = dict(manifest.get("signals") or {})
    source_payload = dict(manifest.get("source") or {})
    raw_last_bar = signals_payload.get("last_bar_utc") or source_payload.get("data_end")
    last_bar = _coerce_timestamp(raw_last_bar)
    if last_bar is None:
        return True
    raw_ttl = config.get("autowfo_staleness_ttl_bars")
    if raw_ttl in (None, ""):
        raw_ttl = runtime_payload.get("staleness_ttl_bars", 1.5)
    try:
        ttl_bars = max(float(raw_ttl), 0.0)
    except Exception:
        ttl_bars = 1.5
    timeframe = source_payload.get("timeframe") or config.get("timeframe") or "2h"
    max_age = _timeframe_to_timedelta(timeframe) * ttl_bars
    compare_ts = reference_ts if reference_ts is not None else pd.Timestamp.now(tz="UTC")
    return compare_ts - last_bar > max_age


def _signal_file_signature(manifest: dict[str, Any]) -> tuple[tuple[str, int, int], ...]:
    signatures: list[tuple[str, int, int]] = []
    signals = dict(manifest.get("signals") or {})
    for raw_path in (signals.get("path"), signals.get("csv_path")):
        if not raw_path:
            continue
        path = Path(str(raw_path)).resolve()
        if not path.exists():
            continue
        stat = path.stat()
        signatures.append((str(path), int(stat.st_mtime_ns), int(stat.st_size)))
    return tuple(signatures)


class _AutowfoBaseStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "2h"
    minimal_roi = {}
    stoploss = -0.99
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    startup_candle_count = 0

    def leverage(
        self,
        pair: str,
        current_time: Any,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        return 1.0

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = dataframe.get("ft_enter_long", 0).fillna(0).astype(int)
        if self.can_short:
            dataframe.loc[:, "enter_short"] = dataframe.get("ft_enter_short", 0).fillna(0).astype(int)
        else:
            dataframe.loc[:, "enter_short"] = 0
        dataframe.loc[dataframe["enter_long"] > 0, "enter_tag"] = "autowfo-long"
        if self.can_short:
            dataframe.loc[dataframe["enter_short"] > 0, "enter_tag"] = "autowfo-short"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = dataframe.get("ft_exit_long", 0).fillna(0).astype(int)
        if self.can_short:
            dataframe.loc[:, "exit_short"] = dataframe.get("ft_exit_short", 0).fillna(0).astype(int)
        else:
            dataframe.loc[:, "exit_short"] = 0
        dataframe.loc[dataframe["exit_long"] > 0, "exit_tag"] = "autowfo-exit-long"
        if self.can_short:
            dataframe.loc[dataframe["exit_short"] > 0, "exit_tag"] = "autowfo-exit-short"
        return dataframe


class _AutowfoGenericSignalStrategyBase(_AutowfoBaseStrategy):
    process_only_new_candles = False
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC",
    }
    _autowfo_manifest: ClassVar[dict[str, Any] | None] = None
    _autowfo_signal_frames: ClassVar[dict[str, pd.DataFrame] | None] = None

    def bot_start(self, **kwargs: Any) -> None:
        manifest_path = _resolve_manifest_path(self.config)
        manifest, signal_frames = _load_signal_bundle(manifest_path)
        self.__class__._autowfo_manifest = manifest
        self.__class__._autowfo_signal_frames = signal_frames

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = str(metadata.get("pair") or "")
        signal_frames = self.__class__._autowfo_signal_frames or {}
        source_pair = _resolve_source_pair(pair, config=self.config, signal_frames=signal_frames)
        return _merge_pair_signals(dataframe, signal_frames.get(source_pair))


class _AutowfoLiveSignalStrategyBase(_AutowfoBaseStrategy):
    process_only_new_candles = True
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC",
    }
    _autowfo_live_cache: ClassVar[dict[str, Any] | None] = None

    @classmethod
    def _load_live_state(cls, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
        manifest_path = _resolve_manifest_path(config)
        manifest_mtime = int(manifest_path.stat().st_mtime_ns)
        cached = cls._autowfo_live_cache
        if cached is not None:
            if cached.get("manifest_path") == str(manifest_path) and cached.get("manifest_mtime") == manifest_mtime:
                current_signature = _signal_file_signature(cached.get("manifest") or {})
                if cached.get("signal_signature") == current_signature:
                    return cached["manifest"], cached["signal_frames"]

        manifest, signal_frames = _load_signal_bundle(manifest_path)
        cls._autowfo_live_cache = {
            "manifest_path": str(manifest_path),
            "manifest_mtime": manifest_mtime,
            "signal_signature": _signal_file_signature(manifest),
            "manifest": manifest,
            "signal_frames": signal_frames,
        }
        return manifest, signal_frames

    def bot_start(self, **kwargs: Any) -> None:
        _resolve_manifest_path(self.config)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        manifest, signal_frames = self.__class__._load_live_state(self.config)
        frame_latest_ts = _coerce_timestamp(dataframe["date"].max()) if "date" in dataframe.columns else None
        if _manifest_is_stale(manifest, self.config, reference_ts=frame_latest_ts):
            return _empty_signal_columns(dataframe)
        pair = str(metadata.get("pair") or "")
        source_pair = _resolve_source_pair(pair, config=self.config, signal_frames=signal_frames)
        return _merge_pair_signals(dataframe, signal_frames.get(source_pair))


class AutowfoGenericSignalStrategyLongOnly(_AutowfoGenericSignalStrategyBase):
    can_short = False


class AutowfoGenericSignalStrategyLongShort(_AutowfoGenericSignalStrategyBase):
    can_short = True


class AutowfoLiveSignalStrategyLongOnly(_AutowfoLiveSignalStrategyBase):
    can_short = False


class AutowfoLiveSignalStrategyLongShort(_AutowfoLiveSignalStrategyBase):
    can_short = True
