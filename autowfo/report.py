"""Report/render helpers extracted from run_btc_regime_sweep monolith."""

import numpy as np
import pandas as pd


def _indicator_combo_label(combo_keys, indicator_meta):
    labels = []
    for key in combo_keys:
        labels.append(indicator_meta.get(key, {}).get("label", key))
    return "+".join(labels)


def _format_indicator_list(value, indicator_meta):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    keys = [k for k in str(value).split(",") if k]
    if not keys:
        return str(value)
    return _indicator_combo_label(keys, indicator_meta)


def _df_to_html(
    df,
    columns,
    label_map,
    filter_name_map,
    regime_name_map,
    regime_type_map,
    format_indicator_list_fn=None,
):
    if format_indicator_list_fn is None:
        raise ValueError("format_indicator_list_fn is required")
    view = df[columns].copy()
    if "filter_name" in view.columns:
        view["filter_name"] = view["filter_name"].map(lambda x: filter_name_map.get(x, x))
    if "indicator_list" in view.columns:
        view["indicator_list"] = view["indicator_list"].map(format_indicator_list_fn)
    if "regime_name" in view.columns:
        view["regime_name"] = view["regime_name"].map(lambda x: regime_name_map.get(x, x))
    if "regime_type" in view.columns:
        view["regime_type"] = view["regime_type"].map(lambda x: regime_type_map.get(x, x))
    for col in view.columns:
        if pd.api.types.is_numeric_dtype(view[col]):
            view[col] = view[col].round(4)
    view = view.fillna("")
    rename = {col: label_map.get(col, col) for col in columns}
    view.rename(columns=rename, inplace=True)
    return view.to_html(index=False, escape=False)


def _format_duration(seconds):
    if seconds is None or np.isnan(seconds):
        return ""
    seconds = int(max(0, seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _plot_portfolio(pf, plot_symbol):
    try:
        return pf.plot(column=plot_symbol, group_by=False, silence_warnings=True)
    except Exception as exc:
        print(f"[warn] plot failed, fallback to value plot: {exc}")
        try:
            value = pf.value()
            if isinstance(value, pd.DataFrame) and plot_symbol in value.columns:
                return value[plot_symbol].vbt.plot()
            return value.vbt.plot()
        except Exception as exc2:
            print(f"[warn] value plot failed, fallback to total return: {exc2}")
            return pf.total_return().vbt.plot()

