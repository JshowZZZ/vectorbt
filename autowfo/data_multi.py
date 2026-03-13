"""Multi-asset OHLCV loader with Parquet cache."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import pandas as pd

if TYPE_CHECKING:
    from autowfo.experiment import Experiment


_REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def _select_parquet_engine() -> str:
    for engine_name in ("pyarrow", "fastparquet"):
        try:
            __import__(engine_name)
            return engine_name
        except Exception:
            continue
    raise RuntimeError(
        "No Parquet engine available. Install 'pyarrow' or 'fastparquet' first."
    )


def _normalize_timestamp(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.tz_convert(None)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_REQUIRED_COLUMNS, index=pd.DatetimeIndex([]))

    view = df.copy()
    view.columns = [str(col).strip().lower() for col in view.columns]
    missing = [col for col in _REQUIRED_COLUMNS if col not in view.columns]
    if missing:
        raise ValueError(f"OHLCV is missing columns: {missing}")

    view = view[_REQUIRED_COLUMNS]
    dt_index = pd.to_datetime(view.index, utc=True, errors="coerce")
    valid_mask = ~dt_index.isna()
    view = view.loc[valid_mask]
    dt_index = dt_index[valid_mask].tz_convert(None)
    view.index = dt_index
    view = view[~view.index.duplicated(keep="last")].sort_index()
    return view


def _normalize_asset_for_filename(asset: str) -> str:
    return str(asset).strip().replace("/", "-").lower()


def _cache_path(
    asset: str,
    timeframe: str,
    exchange: str,
    cache_dir: str | Path,
) -> Path:
    safe_asset = _normalize_asset_for_filename(asset)
    file_name = f"{str(exchange).strip().lower()}_{safe_asset}_{str(timeframe).strip().lower()}.parquet"
    return Path(cache_dir) / file_name


@contextmanager
def _file_lock(lock_path: Path, timeout_seconds: float = 30.0) -> Iterator[None]:
    start_ts = time.monotonic()
    lock_fd = None
    while True:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            if time.monotonic() - start_ts >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for cache lock: {lock_path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _read_parquet(path: Path, engine: str) -> pd.DataFrame:
    return pd.read_parquet(path, engine=engine)


def _write_parquet_atomic(df: pd.DataFrame, path: Path, engine: str) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{time.time_ns()}")
    try:
        df.to_parquet(tmp_path, engine=engine, index=True)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _filter_date_range(
    df: pd.DataFrame,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp | None,
) -> pd.DataFrame:
    out = df.loc[df.index >= start_ts]
    if end_ts is not None:
        out = out.loc[out.index <= end_ts]
    return out


def _covers_date_range(
    df: pd.DataFrame,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp | None,
) -> bool:
    if df.empty:
        return False
    if df.index.min() > start_ts:
        return False
    if end_ts is not None and df.index.max() < end_ts:
        return False
    return True


def _fetch_ohlcv_ccxt(
    asset: str,
    timeframe: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp | None,
    exchange: str,
) -> pd.DataFrame:
    import ccxt  # type: ignore

    exchange_cls = getattr(ccxt, exchange, None)
    if exchange_cls is None:
        raise ValueError(f"Unsupported exchange: {exchange!r}")

    ex = exchange_cls({"enableRateLimit": True})
    try:
        timeframe_sec = int(ex.parse_timeframe(timeframe))
    except Exception:
        timeframe_sec = 3600
    step_ms = max(1, timeframe_sec) * 1000
    since_ms = int(start_ts.tz_localize("UTC").timestamp() * 1000)
    end_ms = int(end_ts.tz_localize("UTC").timestamp() * 1000) if end_ts is not None else None

    rows: list[list[float]] = []
    limit = 1000
    while True:
        batch = ex.fetch_ohlcv(asset, timeframe=timeframe, since=since_ms, limit=limit)
        if not batch:
            break
        rows.extend(batch)

        last_ms = int(batch[-1][0])
        next_since = last_ms + step_ms
        if next_since <= since_ms:
            break
        if end_ms is not None and next_since > end_ms:
            break
        if len(batch) < limit and end_ms is None:
            break
        since_ms = next_since
        if len(batch) < limit and end_ms is not None and last_ms >= end_ms:
            break

    if not rows:
        return pd.DataFrame(columns=_REQUIRED_COLUMNS, index=pd.DatetimeIndex([]))

    out = pd.DataFrame(rows, columns=["timestamp", *_REQUIRED_COLUMNS])
    out.index = pd.to_datetime(out.pop("timestamp"), unit="ms", utc=True).tz_convert(None)
    out = _normalize_ohlcv(out)
    return _filter_date_range(out, start_ts=start_ts, end_ts=end_ts)


def _fetch_ohlcv_vectorbt(
    asset: str,
    timeframe: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp | None,
    exchange: str,
) -> pd.DataFrame:
    import vectorbt as vbt

    data = vbt.CCXTData.download(
        asset,
        exchange=exchange,
        timeframe=timeframe,
        start=start_ts.isoformat(),
        end=end_ts.isoformat() if end_ts is not None else "now UTC",
        show_progress=False,
        config={"enableRateLimit": True},
    )
    out = pd.concat(
        [
            data.get("Open"),
            data.get("High"),
            data.get("Low"),
            data.get("Close"),
            data.get("Volume"),
        ],
        axis=1,
    )
    out.columns = _REQUIRED_COLUMNS
    out = _normalize_ohlcv(out)
    return _filter_date_range(out, start_ts=start_ts, end_ts=end_ts)


def _fetch_ohlcv(
    asset: str,
    timeframe: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp | None,
    exchange: str,
) -> pd.DataFrame:
    try:
        import ccxt  # noqa: F401  # type: ignore
    except Exception:
        return _fetch_ohlcv_vectorbt(asset, timeframe, start_ts, end_ts, exchange)
    return _fetch_ohlcv_ccxt(asset, timeframe, start_ts, end_ts, exchange)


def load_ohlcv(
    asset: str,
    timeframe: str,
    start_date: str,
    end_date: str | None = None,
    exchange: str = "binance",
    cache_dir: str | Path = "artifacts/ohlcv",
) -> pd.DataFrame:
    """Load OHLCV data for one asset and timeframe with Parquet cache."""
    start_ts = _normalize_timestamp(start_date)
    end_ts = _normalize_timestamp(end_date)
    if start_ts is None:
        raise ValueError("start_date is required")
    if end_ts is not None and end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    engine = _select_parquet_engine()
    cache_path = _cache_path(asset=asset, timeframe=timeframe, exchange=exchange, cache_dir=cache_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = cache_path.with_suffix(f"{cache_path.suffix}.lock")

    with _file_lock(lock_path):
        cached = pd.DataFrame(columns=_REQUIRED_COLUMNS, index=pd.DatetimeIndex([]))
        if cache_path.exists():
            cached = _normalize_ohlcv(_read_parquet(cache_path, engine=engine))

        if _covers_date_range(cached, start_ts=start_ts, end_ts=end_ts):
            return _filter_date_range(cached, start_ts=start_ts, end_ts=end_ts)

        fetched = _normalize_ohlcv(
            _fetch_ohlcv(
                asset=asset,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                exchange=exchange,
            )
        )
        merged = fetched if cached.empty else pd.concat([cached, fetched], axis=0)
        merged = _normalize_ohlcv(merged)
        _write_parquet_atomic(merged, cache_path, engine=engine)
        return _filter_date_range(merged, start_ts=start_ts, end_ts=end_ts)


def load_experiment_data(
    experiment: "Experiment",
    start_date: str,
    end_date: str | None = None,
    cache_dir: str | Path = "artifacts/ohlcv",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load trigger/action OHLCV pair for one experiment."""
    config = getattr(experiment, "config", None)
    if not isinstance(config, dict):
        raise TypeError("experiment must provide a .config dict")

    trigger_cfg = config.get("trigger", {})
    action_cfg = config.get("action", {})

    trigger_ohlcv = load_ohlcv(
        asset=str(trigger_cfg.get("asset", "")),
        timeframe=str(trigger_cfg.get("timeframe", "")),
        start_date=start_date,
        end_date=end_date,
        exchange="binance",
        cache_dir=cache_dir,
    )
    action_ohlcv = load_ohlcv(
        asset=str(action_cfg.get("asset", "")),
        timeframe=str(action_cfg.get("timeframe", "")),
        start_date=start_date,
        end_date=end_date,
        exchange="binance",
        cache_dir=cache_dir,
    )
    return trigger_ohlcv, action_ohlcv


def cache_info(cache_dir: str | Path = "artifacts/ohlcv") -> list[dict]:
    """List cached parquet files and their metadata."""
    base_dir = Path(cache_dir)
    if not base_dir.exists():
        return []
    engine = _select_parquet_engine()

    rows = []
    for path in sorted(base_dir.glob("*.parquet")):
        stem = path.stem
        parts = stem.split("_", 2)
        if len(parts) != 3:
            continue
        exchange, asset, timeframe = parts
        df = _normalize_ohlcv(_read_parquet(path, engine=engine))
        rows.append(
            {
                "file": path.name,
                "exchange": exchange,
                "asset": asset,
                "timeframe": timeframe,
                "date_start": df.index.min().isoformat() if not df.empty else None,
                "date_end": df.index.max().isoformat() if not df.empty else None,
                "rows": int(len(df)),
                "size_bytes": int(path.stat().st_size),
            }
        )
    return rows

