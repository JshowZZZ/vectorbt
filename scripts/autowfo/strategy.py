"""Strategy composition helpers extracted from run_btc_regime_sweep monolith."""

import itertools

import numpy as np
import pandas as pd

from scripts.autowfo.constants import INDICATOR_PARAM_FIELDS


def _safe_int(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return int(value)


def _safe_float(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    return float(value)


def _pick_series_from_map(series_map, key, default_key=None):
    if not series_map:
        return pd.Series(dtype=float), None
    if key in series_map:
        return series_map[key], key
    if default_key is not None and default_key in series_map:
        return series_map[default_key], default_key
    try:
        target = float(key)
        keys = sorted(series_map.keys(), key=lambda k: abs(float(k) - target))
    except Exception:
        keys = list(series_map.keys())
    chosen = keys[0]
    return series_map[chosen], chosen


def _coerce_indicator_params(combo_keys, params, ctx):
    params = params.copy()

    def _coerce_lb(field, data_map):
        if field not in params or params[field] is None or not data_map:
            return
        try:
            lb = int(params[field])
        except Exception:
            lb = params[field]
        if lb in data_map:
            return
        try:
            keys = sorted(data_map.keys(), key=lambda k: abs(float(k) - float(lb)))
        except Exception:
            keys = list(data_map.keys())
        if keys:
            params[field] = keys[0]

    if "obv_roc" in combo_keys:
        _coerce_lb("obv_lookback", ctx.get("obv_roc_by_lb"))
    if "volume_z" in combo_keys:
        _coerce_lb("volume_lookback", ctx.get("volume_zscore_by_lb"))
    if "roc" in combo_keys:
        _coerce_lb("roc_lookback", ctx.get("roc_by_lb"))
    if "cmf" in combo_keys:
        _coerce_lb("cmf_lookback", ctx.get("cmf_by_window"))
    if "vroc" in combo_keys:
        _coerce_lb("vroc_lookback", ctx.get("vroc_by_lb"))
    if "ad" in combo_keys:
        _coerce_lb("ad_lookback", ctx.get("ad_roc_by_lb"))
    if "ma_trend" in combo_keys:
        fast = params.get("ma_fast")
        slow = params.get("ma_slow")
        pairs = ctx.get("ma_trend_by_pair", {})
        if pairs and (fast, slow) not in pairs:
            try:
                target = (float(fast), float(slow))
                keys = sorted(
                    pairs.keys(),
                    key=lambda k: abs(float(k[0]) - target[0]) + abs(float(k[1]) - target[1]),
                )
            except Exception:
                keys = list(pairs.keys())
            if keys:
                params["ma_fast"], params["ma_slow"] = keys[0]
    return params


def _build_indicator_param_options_coarse():
    return {
        "volume_z": [
            {"volume_lookback": 12, "volume_z": 0.6},
            {"volume_lookback": 24, "volume_z": 0.9},
        ],
        "obv_roc": [
            {"obv_lookback": 12},
            {"obv_lookback": 24},
        ],
        "cmf": [
            {"cmf_lookback": 20, "cmf_threshold": 0.05},
            {"cmf_lookback": 30, "cmf_threshold": 0.08},
        ],
        "mfi": [
            {"mfi_long": 70, "mfi_short": 30},
            {"mfi_long": 80, "mfi_short": 20},
        ],
        "vroc": [
            {"vroc_lookback": 12, "vroc_threshold": 0.5},
            {"vroc_lookback": 24, "vroc_threshold": 1.0},
        ],
        "ad": [
            {"ad_lookback": 20},
            {"ad_lookback": 40},
        ],
        "rsi": [
            {"rsi_long": 55, "rsi_short": 45},
            {"rsi_long": 60, "rsi_short": 40},
        ],
        "roc": [
            {"roc_lookback": 6, "roc_threshold": 0.01},
            {"roc_lookback": 12, "roc_threshold": 0.02},
        ],
        "macd_hist": [
            {"macd_hist_ratio": 0.001},
            {"macd_hist_ratio": 0.002},
        ],
        "stoch": [
            {"stoch_long": 80, "stoch_short": 20},
            {"stoch_long": 70, "stoch_short": 30},
        ],
        "bb_width": [
            {"bb_width": 0.04},
            {"bb_width": 0.06},
        ],
        "atr_ratio": [
            {"atr_ratio": 0.006},
            {"atr_ratio": 0.01},
        ],
        "ma_trend": [
            {"ma_fast": 10, "ma_slow": 30},
            {"ma_fast": 20, "ma_slow": 50},
        ],
    }


def _expand_float(base, step, min_value=None, max_value=None):
    values = []
    for delta in (-step, 0, step):
        if base is None or (isinstance(base, float) and np.isnan(base)):
            continue
        val = float(base) + float(delta)
        if min_value is not None and val < min_value:
            continue
        if max_value is not None and val > max_value:
            continue
        values.append(round(val, 6))
    return sorted(set(values))


def _expand_int(base, step, min_value=1):
    values = []
    for delta in (-step, 0, step):
        if base is None or (isinstance(base, float) and np.isnan(base)):
            continue
        val = int(round(float(base))) + int(delta)
        if val < min_value:
            continue
        values.append(int(val))
    return sorted(set(values))


def _expand_lookback_list(values, step, min_value=2):
    expanded = set()
    for value in values:
        for delta in (-step, 0, step):
            try:
                val = int(round(float(value))) + int(delta)
            except (TypeError, ValueError):
                continue
            if val < min_value:
                continue
            expanded.add(val)
    return sorted(expanded)


def _expand_pair(base_long, base_short, step, min_value=0, max_value=100):
    longs = _expand_int(base_long, step, min_value=min_value)
    shorts = _expand_int(base_short, step, min_value=min_value)
    pairs = []
    for long_v in longs:
        for short_v in shorts:
            if long_v <= short_v:
                continue
            if long_v > max_value or short_v > max_value:
                continue
            pairs.append((long_v, short_v))
    return sorted(set(pairs))


def _indicator_defaults(options):
    defaults = {}
    for key, opts in options.items():
        if opts:
            defaults[key] = opts[0]
    return defaults


def _refine_indicator_params(ind_key, base_row, steps, defaults):
    base = defaults.get(ind_key, {})
    if ind_key == "rsi":
        long_v = _safe_int(base_row.get("rsi_long"), base.get("rsi_long"))
        short_v = _safe_int(base_row.get("rsi_short"), base.get("rsi_short"))
        pairs = _expand_pair(long_v, short_v, steps["threshold_pair"], min_value=1, max_value=99)
        return [{"rsi_long": p[0], "rsi_short": p[1]} for p in pairs] or [base]
    if ind_key == "stoch":
        long_v = _safe_int(base_row.get("stoch_long"), base.get("stoch_long"))
        short_v = _safe_int(base_row.get("stoch_short"), base.get("stoch_short"))
        pairs = _expand_pair(long_v, short_v, steps["threshold_pair"], min_value=1, max_value=99)
        return [{"stoch_long": p[0], "stoch_short": p[1]} for p in pairs] or [base]
    if ind_key == "mfi":
        long_v = _safe_int(base_row.get("mfi_long"), base.get("mfi_long"))
        short_v = _safe_int(base_row.get("mfi_short"), base.get("mfi_short"))
        pairs = _expand_pair(long_v, short_v, steps["threshold_pair"], min_value=1, max_value=99)
        return [{"mfi_long": p[0], "mfi_short": p[1]} for p in pairs] or [base]
    if ind_key == "bb_width":
        base_val = _safe_float(base_row.get("bb_width"), base.get("bb_width"))
        vals = _expand_float(base_val, steps["bb_width"], min_value=0.0)
        return [{"bb_width": v} for v in vals] or [base]
    if ind_key == "atr_ratio":
        base_val = _safe_float(base_row.get("atr_ratio"), base.get("atr_ratio"))
        vals = _expand_float(base_val, steps["atr_ratio"], min_value=0.0)
        return [{"atr_ratio": v} for v in vals] or [base]
    if ind_key == "macd_hist":
        base_val = _safe_float(base_row.get("macd_hist_ratio"), base.get("macd_hist_ratio"))
        vals = _expand_float(base_val, steps["macd_hist_ratio"], min_value=0.0)
        return [{"macd_hist_ratio": v} for v in vals] or [base]
    if ind_key == "roc":
        lb = _safe_int(base_row.get("roc_lookback"), base.get("roc_lookback"))
        thr = _safe_float(base_row.get("roc_threshold"), base.get("roc_threshold"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        thrs = _expand_float(thr, steps["roc_threshold"], min_value=0.0)
        return [{"roc_lookback": l, "roc_threshold": t} for l in lbs for t in thrs] or [base]
    if ind_key == "obv_roc":
        lb = _safe_int(base_row.get("obv_lookback"), base.get("obv_lookback"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        return [{"obv_lookback": l} for l in lbs] or [base]
    if ind_key == "volume_z":
        lb = _safe_int(base_row.get("volume_lookback"), base.get("volume_lookback"))
        z = _safe_float(base_row.get("volume_z"), base.get("volume_z"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        zs = _expand_float(z, steps["volume_z"], min_value=0.0)
        return [{"volume_lookback": l, "volume_z": v} for l in lbs for v in zs] or [base]
    if ind_key == "cmf":
        lb = _safe_int(base_row.get("cmf_lookback"), base.get("cmf_lookback"))
        thr = _safe_float(base_row.get("cmf_threshold"), base.get("cmf_threshold"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        thrs = _expand_float(thr, steps["cmf_threshold"], min_value=0.0)
        return [{"cmf_lookback": l, "cmf_threshold": t} for l in lbs for t in thrs] or [base]
    if ind_key == "vroc":
        lb = _safe_int(base_row.get("vroc_lookback"), base.get("vroc_lookback"))
        thr = _safe_float(base_row.get("vroc_threshold"), base.get("vroc_threshold"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        thrs = _expand_float(thr, steps["vroc_threshold"], min_value=0.0)
        return [{"vroc_lookback": l, "vroc_threshold": t} for l in lbs for t in thrs] or [base]
    if ind_key == "ad":
        lb = _safe_int(base_row.get("ad_lookback"), base.get("ad_lookback"))
        lbs = _expand_int(lb, steps["lookback"], min_value=2)
        return [{"ad_lookback": l} for l in lbs] or [base]
    if ind_key == "ma_trend":
        fast = _safe_int(base_row.get("ma_fast"), base.get("ma_fast"))
        slow = _safe_int(base_row.get("ma_slow"), base.get("ma_slow"))
        fasts = _expand_int(fast, steps["ma_step"], min_value=2)
        slows = _expand_int(slow, steps["ma_step"], min_value=3)
        pairs = []
        for f in fasts:
            for s in slows:
                if f >= s:
                    continue
                pairs.append((f, s))
        return [{"ma_fast": p[0], "ma_slow": p[1]} for p in sorted(set(pairs))] or [base]
    return [base]


def _iter_indicator_param_combos(combo_keys, param_options):
    param_lists = [param_options.get(key, [{}]) for key in combo_keys]
    for combo_params in itertools.product(*param_lists):
        merged = {field: None for field in INDICATOR_PARAM_FIELDS}
        for params in combo_params:
            merged.update(params)
        yield merged


def _apply_indicator_combo(long_regime, short_regime, combo_keys, combo_params, ctx):
    params_out = {field: combo_params.get(field) for field in INDICATOR_PARAM_FIELDS}

    if "rsi" in combo_keys:
        rsi_long = params_out["rsi_long"]
        rsi_short = params_out["rsi_short"]
        long_regime = long_regime & (ctx["rsi_series"] > rsi_long)
        short_regime = short_regime & (ctx["rsi_series"] < rsi_short)

    if "bb_width" in combo_keys:
        bb_width = params_out["bb_width"]
        long_regime = long_regime & (ctx["bb_width"] > bb_width)
        short_regime = short_regime & (ctx["bb_width"] > bb_width)

    if "atr_ratio" in combo_keys:
        atr_ratio = params_out["atr_ratio"]
        long_regime = long_regime & (ctx["atr_ratio"] > atr_ratio)
        short_regime = short_regime & (ctx["atr_ratio"] > atr_ratio)

    if "ma_trend" in combo_keys:
        ma_pair = (params_out["ma_fast"], params_out["ma_slow"])
        ma_long, ma_short = ctx["ma_trend_by_pair"][ma_pair]
        long_regime = long_regime & ma_long
        short_regime = short_regime & ma_short

    if "macd_hist" in combo_keys:
        macd_hist_ratio = params_out["macd_hist_ratio"]
        long_regime = long_regime & (ctx["macd_hist_ratio_series"] > macd_hist_ratio)
        short_regime = short_regime & (ctx["macd_hist_ratio_series"] < -macd_hist_ratio)

    if "stoch" in combo_keys:
        stoch_long = params_out["stoch_long"]
        stoch_short = params_out["stoch_short"]
        long_regime = long_regime & (ctx["stoch_k"] > stoch_long)
        short_regime = short_regime & (ctx["stoch_k"] < stoch_short)

    if "obv_roc" in combo_keys:
        obv_lookback = params_out["obv_lookback"]
        obv_roc = ctx["obv_roc_by_lb"][obv_lookback]
        long_regime = long_regime & (obv_roc > 0)
        short_regime = short_regime & (obv_roc < 0)

    if "volume_z" in combo_keys:
        volume_lookback = params_out["volume_lookback"]
        volume_z = params_out["volume_z"]
        vol_zscore = ctx["volume_zscore_by_lb"][volume_lookback]
        long_regime = long_regime & (vol_zscore > volume_z)
        short_regime = short_regime & (vol_zscore > volume_z)

    if "roc" in combo_keys:
        roc_lookback = params_out["roc_lookback"]
        roc_threshold = params_out["roc_threshold"]
        roc = ctx["roc_by_lb"][roc_lookback]
        long_regime = long_regime & (roc > roc_threshold)
        short_regime = short_regime & (roc < -roc_threshold)

    if "mfi" in combo_keys:
        mfi_long = params_out["mfi_long"]
        mfi_short = params_out["mfi_short"]
        mfi_series = ctx["mfi_by_window"][ctx["mfi_window"]]
        long_regime = long_regime & (mfi_series > mfi_long)
        short_regime = short_regime & (mfi_series < mfi_short)

    if "cmf" in combo_keys:
        cmf_lookback = params_out["cmf_lookback"]
        cmf_threshold = params_out["cmf_threshold"]
        cmf = ctx["cmf_by_window"][cmf_lookback]
        long_regime = long_regime & (cmf > cmf_threshold)
        short_regime = short_regime & (cmf < -cmf_threshold)

    if "vroc" in combo_keys:
        vroc_lookback = params_out["vroc_lookback"]
        vroc_threshold = params_out["vroc_threshold"]
        vroc = ctx["vroc_by_lb"][vroc_lookback]
        long_regime = long_regime & (vroc > vroc_threshold)
        short_regime = short_regime & (vroc > vroc_threshold)

    if "ad" in combo_keys:
        ad_lookback = params_out["ad_lookback"]
        ad_roc = ctx["ad_roc_by_lb"][ad_lookback]
        long_regime = long_regime & (ad_roc > 0)
        short_regime = short_regime & (ad_roc < 0)

    return long_regime, short_regime, params_out
