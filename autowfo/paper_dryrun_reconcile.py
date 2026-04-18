"""Daily reconciliation between Freqtrade dry-run trades and AUTOWFO live signals."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from autowfo import freqtrade_bridge
from autowfo import live_signal_producer


DRYRUN_RECONCILE_SCHEMA_VERSION = "1.0.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _parse_utc_timestamp(value: Any) -> pd.Timestamp | None:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.tz_localize(None)


def _resolve_reconcile_day(day_utc: str | None = None) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    if str(day_utc or "").strip():
        start = pd.Timestamp(str(day_utc).strip())
    else:
        start = pd.Timestamp.utcnow().tz_localize(None).normalize()
    if start.tzinfo is not None:
        start = start.tz_convert(None)
    start = start.normalize()
    end = start + pd.Timedelta(days=1)
    return start, end, start.strftime("%Y%m%d")


def _default_freqtrade_root() -> Path:
    return Path(__file__).resolve().parents[2] / "freqtrade"


def _load_json_file(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).resolve().read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def load_live_manifest(path: str | Path) -> dict[str, Any]:
    return _load_json_file(path)


def load_freqtrade_config(path: str | Path) -> dict[str, Any]:
    return _load_json_file(path)


def _resolve_sqlite_path(raw_value: str, *, base_dir: Path) -> Path:
    text = str(raw_value or "").strip()
    if text.startswith("sqlite:///"):
        text = text[len("sqlite:///") :]
    if not text:
        return base_dir / "tradesv3.dryrun.sqlite"
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def resolve_freqtrade_db_path(
    *,
    db_path: str | Path | None = None,
    freqtrade_config_path: str | Path | None = None,
    freqtrade_config: Mapping[str, Any] | None = None,
) -> Path:
    if db_path is not None and str(db_path).strip():
        candidate = Path(str(db_path))
        if candidate.is_absolute():
            return candidate.resolve()
        base_dir = Path(freqtrade_config_path).resolve().parents[1] if freqtrade_config_path else _default_freqtrade_root()
        return (base_dir / candidate).resolve()

    config_dir = Path(freqtrade_config_path).resolve().parent if freqtrade_config_path else (_default_freqtrade_root() / "user_data")
    base_dir = config_dir.parent
    config_payload = dict(freqtrade_config or {})
    raw_db_url = config_payload.get("db_url")
    if raw_db_url not in (None, ""):
        return _resolve_sqlite_path(str(raw_db_url), base_dir=base_dir)
    return (base_dir / "tradesv3.dryrun.sqlite").resolve()


def load_freqtrade_trades(db_path: str | Path) -> pd.DataFrame:
    resolved_path = Path(db_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Freqtrade dry-run DB not found: {resolved_path}")
    conn = sqlite3.connect(f"file:{resolved_path.as_posix()}?mode=ro", uri=True)
    try:
        frame = pd.read_sql_query(
            """
SELECT
    id,
    pair,
    is_open,
    open_rate,
    close_rate,
    open_date,
    close_date,
    close_profit,
    close_profit_abs,
    stake_amount,
    amount,
    exit_reason,
    strategy,
    enter_tag,
    timeframe,
    trading_mode,
    leverage,
    is_short,
    fee_open_cost,
    fee_close_cost
FROM trades
ORDER BY open_date ASC
""",
            conn,
        )
    finally:
        conn.close()
    if frame.empty:
        return frame
    normalized = frame.copy()
    normalized["open_date"] = pd.to_datetime(normalized["open_date"], utc=True, errors="coerce").dt.tz_localize(None)
    normalized["close_date"] = pd.to_datetime(normalized["close_date"], utc=True, errors="coerce").dt.tz_localize(None)
    normalized["pair"] = normalized["pair"].astype(str)
    normalized["is_open"] = normalized["is_open"].fillna(False).astype(bool)
    normalized["is_short"] = normalized["is_short"].fillna(False).astype(bool)
    return normalized


def build_pair_mapping(freqtrade_config: Mapping[str, Any]) -> dict[str, str]:
    raw_mapping = freqtrade_config.get("autowfo_pair_mapping") or {}
    if not isinstance(raw_mapping, Mapping):
        return {}
    return {
        str(source).strip(): str(target).strip()
        for source, target in raw_mapping.items()
        if str(source).strip() and str(target).strip()
    }


def _reverse_pair_mapping(pair_mapping: Mapping[str, str]) -> dict[str, str]:
    return {target: source for source, target in pair_mapping.items()}


def load_reconcile_signal_frame(live_manifest: Mapping[str, Any], *, cwd: str | Path | None = None) -> pd.DataFrame:
    source_bundle_manifest = str(live_manifest.get("source_bundle_manifest") or "").strip()
    if not source_bundle_manifest:
        raise ValueError("live manifest is missing source_bundle_manifest")
    bundle_manifest = freqtrade_bridge.load_signal_bundle_manifest(source_bundle_manifest)
    main_run, selected_row = live_signal_producer.load_bundle_replay_inputs(bundle_manifest)
    reconstructed = freqtrade_bridge.reconstruct_frozen_lane(
        main_run,
        selected_row=selected_row,
        cwd=cwd,
        rolling_window=True,
    )
    signal_df = reconstructed["signal_df"].copy()
    signal_df["date"] = pd.to_datetime(signal_df["date"], utc=True, errors="coerce").dt.tz_localize(None)
    signal_df = signal_df.sort_values(["pair", "date"]).reset_index(drop=True)
    return signal_df


def _prepare_signal_frame_for_freqtrade(signal_df: pd.DataFrame) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df.copy()
    prepared = signal_df.copy()
    for column in ("signal_long", "signal_short", "exit_long", "exit_short"):
        prepared[column] = prepared.get(column, 0).fillna(0).astype(int)
    prepared["ft_signal_exit_long"] = (
        prepared.groupby("pair", sort=False)["exit_long"].shift(-1, fill_value=0).astype(int)
    )
    prepared["ft_signal_exit_short"] = (
        prepared.groupby("pair", sort=False)["exit_short"].shift(-1, fill_value=0).astype(int)
    )
    return prepared


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


def _resolve_signal_action(row: Mapping[str, Any], *, long_column: str, short_column: str) -> str:
    try:
        long_value = int(row.get(long_column, 0) or 0)
    except Exception:
        long_value = 0
    try:
        short_value = int(row.get(short_column, 0) or 0)
    except Exception:
        short_value = 0
    if short_value > 0:
        return short_column
    if long_value > 0:
        return long_column
    return "flat"


def _lookup_signal_match(
    signal_frames: dict[str, pd.DataFrame],
    *,
    source_pair: str,
    event_ts: pd.Timestamp | None,
    timeframe_delta: pd.Timedelta,
    long_column: str,
    short_column: str,
    is_short: bool,
    signal_offset: pd.Timedelta | None = None,
) -> dict[str, Any]:
    if event_ts is None:
        return {
            "source_pair": source_pair,
            "signal_bar_utc": None,
            "matched": False,
            "expected_action": "missing",
            "drift_seconds": None,
            "signal_row_found": False,
        }
    resolved_signal_offset = signal_offset if signal_offset is not None else pd.Timedelta(0)
    reference_ts = event_ts - resolved_signal_offset
    pair_frame = signal_frames.get(source_pair)
    if pair_frame is None or pair_frame.empty:
        return {
            "source_pair": source_pair,
            "signal_bar_utc": None,
            "matched": False,
            "expected_action": "missing",
            "drift_seconds": None,
            "signal_row_found": False,
        }
    dates = pair_frame["date"]
    idx = int(dates.searchsorted(reference_ts, side="right") - 1)
    if idx < 0:
        return {
            "source_pair": source_pair,
            "signal_bar_utc": None,
            "matched": False,
            "expected_action": "missing",
            "drift_seconds": None,
            "signal_row_found": False,
        }
    row = pair_frame.iloc[idx]
    signal_bar = row["date"]
    if reference_ts - signal_bar > timeframe_delta:
        return {
            "source_pair": source_pair,
            "signal_bar_utc": signal_bar.isoformat() if pd.notna(signal_bar) else None,
            "matched": False,
            "expected_action": "stale",
            "drift_seconds": float((event_ts - signal_bar).total_seconds()) if pd.notna(signal_bar) else None,
            "signal_row_found": False,
        }
    expected_action = _resolve_signal_action(row, long_column=long_column, short_column=short_column)
    matched = (expected_action == short_column) if is_short else (expected_action == long_column)
    return {
        "source_pair": source_pair,
        "signal_bar_utc": signal_bar.isoformat() if pd.notna(signal_bar) else None,
        "matched": bool(matched),
        "expected_action": expected_action,
        "drift_seconds": float((event_ts - signal_bar).total_seconds()) if pd.notna(signal_bar) else None,
        "signal_row_found": True,
    }


def build_daily_reconcile_summary(
    trades_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    *,
    day_start: pd.Timestamp,
    day_end: pd.Timestamp,
    pair_mapping: Mapping[str, str],
    live_manifest: Mapping[str, Any],
    db_path: str | Path,
) -> dict[str, Any]:
    reverse_mapping = _reverse_pair_mapping(pair_mapping)
    timeframe_delta = _timeframe_to_timedelta((live_manifest.get("source") or {}).get("timeframe") or "2h")
    prepared_signal_df = _prepare_signal_frame_for_freqtrade(signal_df)
    signal_frames = {
        str(pair): group.reset_index(drop=True)
        for pair, group in prepared_signal_df.sort_values(["pair", "date"]).groupby("pair", sort=False)
    }

    opened = trades_df.loc[(trades_df["open_date"] >= day_start) & (trades_df["open_date"] < day_end)].copy()
    closed = trades_df.loc[(trades_df["close_date"] >= day_start) & (trades_df["close_date"] < day_end)].copy()
    open_now = trades_df.loc[trades_df["is_open"]].copy()

    opened_records: list[dict[str, Any]] = []
    closed_records: list[dict[str, Any]] = []

    for _, row in opened.iterrows():
        source_pair = reverse_mapping.get(str(row.get("pair") or ""), str(row.get("pair") or ""))
        match = _lookup_signal_match(
            signal_frames,
            source_pair=source_pair,
            event_ts=row.get("open_date"),
            timeframe_delta=timeframe_delta,
            long_column="signal_long",
            short_column="signal_short",
            is_short=bool(row.get("is_short")),
            signal_offset=timeframe_delta,
        )
        opened_records.append(
            {
                "trade_id": int(row.get("id")),
                "pair": str(row.get("pair") or ""),
                "source_pair": source_pair,
                "direction": "Short" if bool(row.get("is_short")) else "Long",
                "open_date": row.get("open_date").isoformat() if pd.notna(row.get("open_date")) else None,
                "open_rate": float(row.get("open_rate")) if pd.notna(row.get("open_rate")) else None,
                "stake_amount": float(row.get("stake_amount")) if pd.notna(row.get("stake_amount")) else None,
                "enter_tag": str(row.get("enter_tag") or ""),
                **match,
            }
        )

    for _, row in closed.iterrows():
        source_pair = reverse_mapping.get(str(row.get("pair") or ""), str(row.get("pair") or ""))
        match = _lookup_signal_match(
            signal_frames,
            source_pair=source_pair,
            event_ts=row.get("close_date"),
            timeframe_delta=timeframe_delta,
            long_column="ft_signal_exit_long",
            short_column="ft_signal_exit_short",
            is_short=bool(row.get("is_short")),
            signal_offset=timeframe_delta,
        )
        closed_records.append(
            {
                "trade_id": int(row.get("id")),
                "pair": str(row.get("pair") or ""),
                "source_pair": source_pair,
                "direction": "Short" if bool(row.get("is_short")) else "Long",
                "close_date": row.get("close_date").isoformat() if pd.notna(row.get("close_date")) else None,
                "close_rate": float(row.get("close_rate")) if pd.notna(row.get("close_rate")) else None,
                "close_profit": float(row.get("close_profit")) if pd.notna(row.get("close_profit")) else None,
                "close_profit_abs": float(row.get("close_profit_abs")) if pd.notna(row.get("close_profit_abs")) else None,
                "exit_reason": str(row.get("exit_reason") or ""),
                **match,
            }
        )

    opened_match_count = sum(1 for row in opened_records if row.get("matched"))
    closed_match_count = sum(1 for row in closed_records if row.get("matched"))
    opened_missing_count = sum(1 for row in opened_records if not row.get("signal_row_found"))
    closed_missing_count = sum(1 for row in closed_records if not row.get("signal_row_found"))

    entry_drifts = [float(row["drift_seconds"]) for row in opened_records if row.get("drift_seconds") is not None]
    exit_drifts = [float(row["drift_seconds"]) for row in closed_records if row.get("drift_seconds") is not None]

    pair_summary = []
    all_pairs = sorted(set(opened["pair"].astype(str).tolist()) | set(closed["pair"].astype(str).tolist()))
    for pair in all_pairs:
        opened_pair = [row for row in opened_records if row.get("pair") == pair]
        closed_pair = [row for row in closed_records if row.get("pair") == pair]
        pair_summary.append(
            {
                "pair": pair,
                "source_pair": reverse_mapping.get(pair, pair),
                "opened_count": len(opened_pair),
                "closed_count": len(closed_pair),
                "entry_match_count": sum(1 for row in opened_pair if row.get("matched")),
                "exit_match_count": sum(1 for row in closed_pair if row.get("matched")),
                "realized_profit_abs_sum": float(sum((row.get("close_profit_abs") or 0.0) for row in closed_pair)),
            }
        )

    totals = {
        "db_trade_count": int(len(trades_df)),
        "open_positions_current": int(len(open_now)),
        "opened_trades_day": int(len(opened_records)),
        "closed_trades_day": int(len(closed_records)),
        "opened_long_day": int((~opened["is_short"]).sum()) if not opened.empty else 0,
        "opened_short_day": int(opened["is_short"].sum()) if not opened.empty else 0,
        "closed_long_day": int((~closed["is_short"]).sum()) if not closed.empty else 0,
        "closed_short_day": int(closed["is_short"].sum()) if not closed.empty else 0,
        "realized_profit_abs_sum": float(pd.to_numeric(closed.get("close_profit_abs"), errors="coerce").fillna(0.0).sum()) if not closed.empty else 0.0,
        "realized_profit_ratio_mean": float(pd.to_numeric(closed.get("close_profit"), errors="coerce").dropna().mean()) if not closed.empty and pd.to_numeric(closed.get("close_profit"), errors="coerce").dropna().size else None,
        "entry_signal_match_count": int(opened_match_count),
        "entry_signal_match_rate": float(opened_match_count / len(opened_records)) if opened_records else None,
        "entry_signal_missing_count": int(opened_missing_count),
        "exit_signal_match_count": int(closed_match_count),
        "exit_signal_match_rate": float(closed_match_count / len(closed_records)) if closed_records else None,
        "exit_signal_missing_count": int(closed_missing_count),
        "entry_drift_seconds_mean": float(sum(entry_drifts) / len(entry_drifts)) if entry_drifts else None,
        "exit_drift_seconds_mean": float(sum(exit_drifts) / len(exit_drifts)) if exit_drifts else None,
    }

    return {
        "schema_version": DRYRUN_RECONCILE_SCHEMA_VERSION,
        "created_utc": _utc_now_iso(),
        "date_utc": day_start.strftime("%Y-%m-%d"),
        "window_start_utc": day_start.isoformat(),
        "window_end_utc": day_end.isoformat(),
        "db_path": str(Path(db_path).resolve()),
        "live_manifest_path": str(Path(str(live_manifest.get("_path") or "")).resolve()) if live_manifest.get("_path") else None,
        "source_bundle_manifest": str(live_manifest.get("source_bundle_manifest") or ""),
        "analysis": dict(live_manifest.get("analysis") or {}),
        "source": dict(live_manifest.get("source") or {}),
        "runtime": dict(live_manifest.get("runtime") or {}),
        "pair_mapping": dict(pair_mapping),
        "totals": totals,
        "pair_summary": pair_summary,
        "opened_trades": opened_records,
        "closed_trades": closed_records,
    }


def reconcile_dryrun_day(
    *,
    live_manifest_path: str | Path,
    out_dir: str | Path,
    freqtrade_config_path: str | Path | None = None,
    db_path: str | Path | None = None,
    day_utc: str | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    live_manifest = load_live_manifest(live_manifest_path)
    live_manifest["_path"] = str(Path(live_manifest_path).resolve())
    config_path = Path(freqtrade_config_path).resolve() if freqtrade_config_path else (_default_freqtrade_root() / "user_data" / "config_autowfo_dryrun.json")
    freqtrade_config = load_freqtrade_config(config_path)
    resolved_db_path = resolve_freqtrade_db_path(
        db_path=db_path,
        freqtrade_config_path=config_path,
        freqtrade_config=freqtrade_config,
    )
    trades_df = load_freqtrade_trades(resolved_db_path)
    signal_df = load_reconcile_signal_frame(live_manifest, cwd=cwd)
    day_start, day_end, day_label = _resolve_reconcile_day(day_utc)
    summary = build_daily_reconcile_summary(
        trades_df,
        signal_df,
        day_start=day_start,
        day_end=day_end,
        pair_mapping=build_pair_mapping(freqtrade_config),
        live_manifest=live_manifest,
        db_path=resolved_db_path,
    )
    output_dir = Path(out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"daily_summary_{day_label}.json"
    _atomic_write_json(out_path, summary)
    summary["out_path"] = str(out_path)
    return summary
