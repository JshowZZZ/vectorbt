"""Data refresh submodule for control_panel (AWF-113)."""

import json
import sys as _sys
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus


def _cp():
    """Deferred accessor for the main control_panel module."""
    return _sys.modules.get('scripts.control_panel')


def _data_refresh_state_path():
    return _cp().ARTIFACTS / "data_refresh_state.json"


def _default_data_refresh_state():
    return {
        "ok": True,
        "reason": "",
        "updated_utc": "",
        "last_refresh_utc": "",
        "next_refresh_utc": "",
        "exchange": "",
        "base_symbol": "",
        "timeframes": [],
        "symbols": [],
        "timeframe_data_end": {},
        "pair_data_end": [],
        "errors": [],
    }


def _read_data_refresh_state():
    cp = _cp()
    state = cp._read_json_file(_data_refresh_state_path(), _default_data_refresh_state())
    if not isinstance(state, dict):
        state = _default_data_refresh_state()
    template = _default_data_refresh_state()
    for key, val in template.items():
        state.setdefault(key, val)
    if not isinstance(state.get("timeframe_data_end"), dict):
        state["timeframe_data_end"] = {}
    if not isinstance(state.get("pair_data_end"), list):
        state["pair_data_end"] = []
    if not isinstance(state.get("errors"), list):
        state["errors"] = []
    return state


def _write_data_refresh_state(state):
    cp = _cp()
    payload = _default_data_refresh_state()
    if isinstance(state, dict):
        payload.update(state)
    cp.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _data_refresh_state_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _resolve_data_refresh_plan(cfg):
    from scripts.autowfo.engine_helpers import DEFAULT_CONFIG
    cfg = cfg if isinstance(cfg, dict) else {}
    exchange = str(cfg.get("exchange") or "binance").strip() or "binance"
    base_symbol = str(cfg.get("base_symbol") or "BTC/USDT").strip() or "BTC/USDT"

    timeframes = []
    raw_timeframes = cfg.get("timeframes")
    if isinstance(raw_timeframes, list):
        for item in raw_timeframes:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            if not timeframe:
                continue
            try:
                days = int(item.get("days", 0))
            except Exception:
                days = 0
            if days <= 0:
                days = 1
            timeframes.append({"timeframe": timeframe, "days": days})
    if not timeframes:
        timeframes = [dict(item) for item in DEFAULT_CONFIG.get("timeframes", []) if isinstance(item, dict)]

    symbols = []
    raw_symbols = cfg.get("trade_symbols")
    if isinstance(raw_symbols, str):
        raw_symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]
    if isinstance(raw_symbols, (list, tuple)):
        for item in raw_symbols:
            symbol = str(item).strip()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    if not symbols:
        fallback = DEFAULT_CONFIG.get("trade_symbols", [])
        if isinstance(fallback, list):
            symbols = [str(item).strip() for item in fallback if str(item).strip()]

    return {
        "exchange": exchange,
        "base_symbol": base_symbol,
        "timeframes": timeframes,
        "trade_symbols": symbols,
    }


def _refresh_data_cache_now(force=False, reason="auto", refresh_ohlcv_cache_fn=None):
    cp = _cp()
    with cp.DATA_REFRESH_LOCK:
        state = _read_data_refresh_state()
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        last_refresh = cp._parse_iso(state.get("last_refresh_utc"))
        if not force and last_refresh is not None:
            if last_refresh.tzinfo is None:
                last_refresh = last_refresh.replace(tzinfo=timezone.utc)
            elapsed = (now_utc - last_refresh.astimezone(timezone.utc)).total_seconds()
            if elapsed < cp.DATA_REFRESH_INTERVAL_SECONDS:
                state["next_refresh_utc"] = (
                    last_refresh.astimezone(timezone.utc) + timedelta(seconds=cp.DATA_REFRESH_INTERVAL_SECONDS)
                ).replace(microsecond=0).isoformat()
                _write_data_refresh_state(state)
                return state, False

        plan = _resolve_data_refresh_plan(cp._read_config())
        exchange = plan["exchange"]
        base_symbol = plan["base_symbol"]
        timeframes = plan["timeframes"]
        symbols = plan["trade_symbols"]

        if refresh_ohlcv_cache_fn is None:
            from scripts.autowfo import data as autowfo_data

            cache_format = "parquet" if autowfo_data._has_parquet_engine() else "csv"
            refresh_ohlcv_cache_fn = autowfo_data.refresh_ohlcv_cache
        else:
            cache_format = "csv"

        try:
            refresh_payload = refresh_ohlcv_cache_fn(
                exchange=exchange,
                timeframes=timeframes,
                symbols=symbols,
                base_symbol=base_symbol,
                cache_dir=str(cp.ARTIFACTS / "cache_ccxt"),
                cache_format=cache_format,
            )
            if not isinstance(refresh_payload, dict):
                refresh_payload = {}
            refreshed_state = _default_data_refresh_state()
            refreshed_state["ok"] = True
            refreshed_state["reason"] = str(reason or "")
            refreshed_state["updated_utc"] = now_utc.isoformat()
            refreshed_state["last_refresh_utc"] = now_utc.isoformat()
            refreshed_state["next_refresh_utc"] = (
                now_utc + timedelta(seconds=cp.DATA_REFRESH_INTERVAL_SECONDS)
            ).replace(microsecond=0).isoformat()
            refreshed_state["exchange"] = exchange
            refreshed_state["base_symbol"] = base_symbol
            refreshed_state["timeframes"] = timeframes
            refreshed_state["symbols"] = symbols
            refreshed_state["timeframe_data_end"] = dict(refresh_payload.get("timeframe_data_end") or {})
            refreshed_state["pair_data_end"] = list(refresh_payload.get("pair_data_end") or [])
            refreshed_state["errors"] = list(refresh_payload.get("errors") or [])
            _write_data_refresh_state(refreshed_state)
            return refreshed_state, True
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append(str(exc))
            state["ok"] = False
            state["reason"] = str(reason or "")
            state["updated_utc"] = now_utc.isoformat()
            state["last_refresh_utc"] = now_utc.isoformat()
            state["next_refresh_utc"] = (
                now_utc + timedelta(seconds=cp.DATA_REFRESH_INTERVAL_SECONDS)
            ).replace(microsecond=0).isoformat()
            state["errors"] = errors[-50:]
            _write_data_refresh_state(state)
            return state, False


def _data_refresh_loop():
    cp = _cp()
    while not cp.DATA_REFRESH_STOP.wait(5):
        try:
            _refresh_data_cache_now(force=False, reason="auto")
        except Exception:
            # Keep daemon loop resilient; failures are recorded in refresh state.
            pass


def _ensure_data_refresh_thread():
    cp = _cp()
    with cp.DATA_REFRESH_THREAD_LOCK:
        if cp.DATA_REFRESH_THREAD is not None and cp.DATA_REFRESH_THREAD.is_alive():
            return
        cp.DATA_REFRESH_STOP.clear()
        cp.DATA_REFRESH_THREAD = threading.Thread(
            target=_data_refresh_loop,
            name="autowfo-data-refresh",
            daemon=True,
        )
        cp.DATA_REFRESH_THREAD.start()


def _overlay_data_end_from_refresh(rows, refresh_state):
    if not isinstance(rows, list):
        return
    refresh_state = refresh_state if isinstance(refresh_state, dict) else {}
    timeframe_lookup = refresh_state.get("timeframe_data_end")
    if not isinstance(timeframe_lookup, dict):
        timeframe_lookup = {}

    pair_lookup = {}
    raw_pairs = refresh_state.get("pair_data_end")
    if isinstance(raw_pairs, list):
        for item in raw_pairs:
            if not isinstance(item, dict):
                continue
            timeframe = str(item.get("timeframe", "")).strip()
            symbol = str(item.get("symbol", "")).strip()
            data_end = str(item.get("data_end", "")).strip()
            if timeframe and symbol and data_end:
                pair_lookup[(timeframe, symbol)] = data_end

    for row in rows:
        if not isinstance(row, dict):
            continue
        timeframe = str(row.get("timeframe", "")).strip()
        if not timeframe:
            continue
        data_end = ""
        for symbol_key in ("plot_symbol", "symbol", "trade_symbol"):
            symbol = str(row.get(symbol_key, "")).strip()
            if symbol:
                data_end = pair_lookup.get((timeframe, symbol), "")
                if data_end:
                    break
        if not data_end:
            data_end = str(timeframe_lookup.get(timeframe, "")).strip()
        if data_end:
            row["data_end"] = data_end


def try_handle_get(handler, _parsed, path):
    if path == "/data/refresh.json":
        handler._send(json.dumps(_read_data_refresh_state(), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    return False


def try_handle_post(handler, parsed):
    if parsed.path == "/data/refresh":
        cp = _cp()
        _ensure_data_refresh_thread()
        try:
            payload = handler._read_json_payload()
        except Exception:
            payload = {}
        force = bool(payload.get("force", False))
        reason = str(payload.get("reason", "manual") or "manual")
        state, refreshed = _refresh_data_cache_now(force=force, reason=reason)
        handler._send(
            json.dumps(
                {"ok": bool(state.get("ok", True)), "refreshed": bool(refreshed), "state": state},
                ensure_ascii=False,
            ),
            "application/json; charset=utf-8",
            status=HTTPStatus.OK if bool(state.get("ok", True)) else HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        return True
    return False


__all__ = [
    "_data_refresh_state_path",
    "_default_data_refresh_state",
    "_read_data_refresh_state",
    "_write_data_refresh_state",
    "_resolve_data_refresh_plan",
    "_refresh_data_cache_now",
    "_data_refresh_loop",
    "_ensure_data_refresh_thread",
    "_overlay_data_end_from_refresh",
    "try_handle_get",
    "try_handle_post",
]
