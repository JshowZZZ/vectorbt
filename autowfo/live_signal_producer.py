"""Live signal store producer for AUTOWFO frozen lanes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from autowfo import data as autowfo_data
from autowfo import freqtrade_bridge
from autowfo import pilot_analysis


LIVE_SIGNAL_MANIFEST_VERSION = "1.0.0"
DEFAULT_STALENESS_TTL_BARS = 1.5
DEFAULT_MIN_TAIL_BARS = 3


def _resolve_selected_row(manifest: Mapping[str, Any]) -> dict[str, Any]:
    selected_row = dict((manifest.get("analysis") or {}).get("selected_row") or {})
    if not selected_row:
        raise ValueError("bundle manifest is missing analysis.selected_row")
    return selected_row


def _resolve_main_run(manifest: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(manifest.get("source") or {})
    run_root = str(source.get("run_root") or "").strip()
    if not run_root:
        main_run_id = str((manifest.get("analysis") or {}).get("main_run_id") or "").strip()
        if not main_run_id:
            raise ValueError("bundle manifest is missing source.run_root and analysis.main_run_id")
        return pilot_analysis.load_run_analysis_inputs(main_run_id)
    return pilot_analysis.load_run_analysis_inputs(run_root)


def load_bundle_replay_inputs(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _resolve_main_run(manifest), _resolve_selected_row(manifest)


def _resolve_tail_bars(selected_row: Mapping[str, Any], tail_bars: int | None) -> int:
    derived = max(int(selected_row.get("max_hold") or 1) + 2, DEFAULT_MIN_TAIL_BARS)
    if tail_bars is None:
        return derived
    try:
        resolved = int(tail_bars)
    except Exception:
        return derived
    if resolved <= 0:
        return derived
    return max(resolved, DEFAULT_MIN_TAIL_BARS)


def _tail_signal_frame(signal_df: pd.DataFrame, *, tail_bars: int) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df.copy()
    ordered = signal_df.copy()
    ordered["date"] = pd.to_datetime(ordered["date"], utc=True, errors="coerce").dt.tz_localize(None)
    ordered = ordered.sort_values(["pair", "date"]).reset_index(drop=True)
    tailed = ordered.groupby("pair", sort=False, group_keys=False).tail(int(tail_bars)).reset_index(drop=True)
    return tailed


def _live_strategy_name(has_short_signals: bool) -> str:
    return "AutowfoLiveSignalStrategyLongShort" if has_short_signals else "AutowfoLiveSignalStrategyLongOnly"


def export_live_signal_store(
    bundle_manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path,
    out_dir: str | Path,
    cwd: str | Path | None = None,
    tail_bars: int | None = None,
    staleness_ttl_bars: float = DEFAULT_STALENESS_TTL_BARS,
) -> dict[str, Any]:
    main_run, selected_row = load_bundle_replay_inputs(bundle_manifest)
    reconstructed = freqtrade_bridge.reconstruct_frozen_lane(
        main_run,
        selected_row=selected_row,
        cwd=cwd,
        rolling_window=True,
    )
    resolved_tail_bars = _resolve_tail_bars(selected_row, tail_bars)
    signal_df = _tail_signal_frame(reconstructed["signal_df"], tail_bars=resolved_tail_bars)
    output_dir = Path(out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    signal_csv_path = output_dir / "current_signals.csv"
    signal_df.to_csv(signal_csv_path, index=False)

    signal_parquet_path = output_dir / "current_signals.parquet"
    primary_format = "csv"
    signal_path = ""
    if autowfo_data._has_parquet_engine():
        signal_df.to_parquet(signal_parquet_path, index=False)
        primary_format = "parquet"
        signal_path = str(signal_parquet_path)

    last_bar_utc = (
        freqtrade_bridge._normalize_timestamp_value(signal_df["date"].max()) if not signal_df.empty else None
    )
    live_manifest_path = output_dir / "live_manifest.json"
    live_manifest = {
        "schema_version": LIVE_SIGNAL_MANIFEST_VERSION,
        "created_utc": freqtrade_bridge._utc_now_iso(),
        "source_bundle_manifest": str(Path(manifest_path).resolve()),
        "analysis": dict(bundle_manifest.get("analysis") or {}),
        "source": {
            **dict(bundle_manifest.get("source") or {}),
            "data_start": (
                freqtrade_bridge._normalize_timestamp_value(signal_df["date"].min())
                if not signal_df.empty
                else None
            ),
            "data_end": last_bar_utc,
        },
        "replay_contract": dict(bundle_manifest.get("replay_contract") or {}),
        "signals": {
            "primary_format": primary_format,
            "path": signal_path,
            "csv_path": str(signal_csv_path),
            "rows": int(len(signal_df)),
            "columns": list(signal_df.columns),
            "pairs": sorted(signal_df["pair"].dropna().astype(str).unique().tolist()),
            "has_short_signals": bool(reconstructed["has_short_signals"]),
            "enter_long_count": int(signal_df["enter_long"].sum()) if not signal_df.empty else 0,
            "enter_short_count": int(signal_df["enter_short"].sum()) if not signal_df.empty else 0,
            "exit_long_count": int(signal_df["exit_long"].sum()) if not signal_df.empty else 0,
            "exit_short_count": int(signal_df["exit_short"].sum()) if not signal_df.empty else 0,
            "last_bar_utc": last_bar_utc,
        },
        "runtime": {
            "tail_bars_per_pair": int(resolved_tail_bars),
            "staleness_ttl_bars": float(staleness_ttl_bars),
            "rolling_window": True,
            "window_days": selected_row.get("data_days"),
        },
        "autowfo_replay": {
            "summary": reconstructed["summary"],
        },
        "freqtrade": {
            "strategy_path": str((Path(__file__).resolve().parents[1] / "scripts" / "freqtrade_generic_signal_strategy.py")),
            "recommended_strategy": _live_strategy_name(bool(reconstructed["has_short_signals"])),
            "recommended_trading_mode": "futures" if reconstructed["has_short_signals"] else "spot",
        },
    }
    live_manifest_path.write_text(json.dumps(live_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return live_manifest