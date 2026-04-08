"""Extract consolidated summary from all AUTOWFO backtest runs."""
import glob
import json
import os
import csv
from collections import Counter

RUNS_DIR = r"E:/Project/vectorbt-master/artifacts/runs"

# Columns to extract from leaderboard (with fallbacks)
EXTRACT_COLS = {
    "indicator_list": ["indicator_list"],
    "regime_name": ["regime_name"],
    "vol_mode": ["vol_mode"],
    "oos_return": ["oos_avg_total_return_pct", "avg_total_return_pct"],
    "oos_sharpe": ["oos_sharpe_like"],
    "oos_pos_ratio": ["oos_positive_segment_ratio"],
    "oos_drawdown": ["oos_avg_max_drawdown_pct", "avg_max_drawdown_pct"],
    "avg_hold_hours": ["avg_hold_hours", "oos_avg_hold_hours"],
    "trades": ["oos_min_total_trades", "oos_avg_daily_trades", "min_total_trades", "avg_daily_trades"],
    "composite_score": ["composite_score"],
    "tp_stop": ["tp_stop"],
    "sl_stop": ["sl_stop"],
    "max_hold": ["max_hold"],
    "symbol": ["base_symbol", "plot_symbol"],
    "timeframe": ["timeframe"],
    "data_days": ["data_days"],
}


def get_val(row, keys):
    for k in keys:
        v = row.get(k)
        if v is not None and v != "":
            return v
    return ""


def read_leaderboard(run_dir):
    """Find and read the first row of the best leaderboard file."""
    candidates = [
        os.path.join(run_dir, "results", "leaderboard.csv"),
        os.path.join(run_dir, "combo", "leaderboard.csv"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        return row, path
            except Exception:
                continue
    return None, None


def read_sweep_config(run_dir):
    """Read sweep config for supplementary info."""
    candidates = [
        os.path.join(run_dir, "runtime", "sweep_config.snapshot.json"),
        os.path.join(run_dir, "runtime", "sweep_config.json"),
        os.path.join(run_dir, "sweep_config.snapshot.json"),
        os.path.join(run_dir, "sweep_config.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {}


def to_float(v, default=None):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def main():
    run_dirs = sorted(glob.glob(os.path.join(RUNS_DIR, "*")))
    print(f"Found {len(run_dirs)} run directories\n")

    rows = []
    skipped = 0

    for run_dir in run_dirs:
        if not os.path.isdir(run_dir):
            continue
        run_id = os.path.basename(run_dir)
        top1, lb_path = read_leaderboard(run_dir)
        if top1 is None:
            skipped += 1
            continue

        sweep = read_sweep_config(run_dir)

        symbol = get_val(top1, EXTRACT_COLS["symbol"])
        if not symbol:
            # try from sweep config trade_symbols
            ts = sweep.get("trade_symbols", [])
            symbol = ts[0] if ts else "?"

        rec = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": get_val(top1, EXTRACT_COLS["timeframe"]) or "?",
            "indicator_list": get_val(top1, EXTRACT_COLS["indicator_list"]),
            "regime": get_val(top1, EXTRACT_COLS["regime_name"]),
            "oos_return_pct": to_float(get_val(top1, EXTRACT_COLS["oos_return"]), 0),
            "oos_sharpe": to_float(get_val(top1, EXTRACT_COLS["oos_sharpe"])),
            "oos_pos_ratio": to_float(get_val(top1, EXTRACT_COLS["oos_pos_ratio"])),
            "oos_drawdown_pct": to_float(get_val(top1, EXTRACT_COLS["oos_drawdown"])),
            "trades": get_val(top1, EXTRACT_COLS["trades"]),
            "composite_score": to_float(get_val(top1, EXTRACT_COLS["composite_score"])),
            "tp": get_val(top1, EXTRACT_COLS["tp_stop"]),
            "sl": get_val(top1, EXTRACT_COLS["sl_stop"]),
            "max_hold": get_val(top1, EXTRACT_COLS["max_hold"]),
            "source": "results" if "results" in (lb_path or "") else "combo",
        }
        rows.append(rec)

    # Sort by OOS return descending
    rows.sort(key=lambda r: r["oos_return_pct"] or 0, reverse=True)

    print(f"Runs with leaderboard: {len(rows)}")
    print(f"Runs skipped (no leaderboard): {skipped}")
    print()

    # --- Print table ---
    def fmt(v, w, right=False):
        s = str(v) if v is not None else ""
        if len(s) > w:
            s = s[:w-1] + "~"
        return s.rjust(w) if right else s.ljust(w)

    def fmtf(val, spec, width):
        """Format a nullable float with given spec, right-aligned to width."""
        if val is not None:
            return format(val, spec).rjust(width)
        return "N/A".rjust(width)

    def print_row(i, r):
        sharpe_s = fmtf(r["oos_sharpe"], ".3f", 7)
        pos_r_s = fmtf(r["oos_pos_ratio"], ".2f", 6)
        dd_s = fmtf(r["oos_drawdown_pct"], ".2f", 8)
        comp_s = fmtf(r["composite_score"], ".3f", 7)
        ret_s = format(r["oos_return_pct"] or 0, ">9.2f")
        print(
            f"{i:>3} | {fmt(r['run_id'],16)} | {fmt(r['symbol'],12)} | {fmt(r['timeframe'],4)} | "
            f"{fmt(r['indicator_list'],35)} | {fmt(r['regime'],14)} | "
            f"{ret_s} | {sharpe_s} | {pos_r_s} | {dd_s} | "
            f"{fmt(r['trades'],7,True)} | {comp_s} | "
            f"{fmt(r['tp'],6,True)} | {fmt(r['sl'],6,True)} | {fmt(r['max_hold'],3,True)} | "
            f"{fmt(r['source'],7)}"
        )

    header = (
        f"{'#':>3} | {'run_id':<16} | {'symbol':<12} | {'tf':<4} | {'indicator_list':<35} | "
        f"{'regime':<14} | {'oos_ret%':>9} | {'sharpe':>7} | {'pos_r':>6} | "
        f"{'dd%':>8} | {'trades':>7} | {'comp':>7} | {'tp':>6} | {'sl':>6} | {'mh':>3} | {'src':<7}"
    )
    sep = "-" * len(header)

    # Determine what to print
    if len(rows) <= 30:
        display_rows = list(enumerate(rows, 1))
        label = "ALL RUNS"
    else:
        display_rows = list(enumerate(rows[:20], 1))
        label = "TOP 20"

    print(f"=== {label} (sorted by OOS return %) ===")
    print(header)
    print(sep)
    for i, r in display_rows:
        print_row(i, r)

    if len(rows) > 30:
        print("\n=== BOTTOM 5 ===")
        print(header)
        print(sep)
        for i, r in enumerate(rows[-5:], len(rows) - 4):
            print_row(i, r)

    # === SUMMARY STATISTICS ===
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)

    # Count by symbol x timeframe
    sym_tf = Counter()
    for r in rows:
        sym_tf[(r["symbol"], r["timeframe"])] += 1
    print("\n--- Runs by Symbol x Timeframe ---")
    for (sym, tf), cnt in sorted(sym_tf.items(), key=lambda x: -x[1]):
        print(f"  {sym:<14} {tf:<5} : {cnt}")

    # Positive OOS return
    pos = sum(1 for r in rows if (r["oos_return_pct"] or 0) > 0)
    neg = sum(1 for r in rows if (r["oos_return_pct"] or 0) < 0)
    zero = len(rows) - pos - neg
    print(f"\n--- OOS Return Distribution ---")
    print(f"  Positive: {pos} ({100*pos/len(rows):.1f}%)")
    print(f"  Negative: {neg} ({100*neg/len(rows):.1f}%)")
    print(f"  Zero:     {zero}")

    # Average OOS return
    oos_vals = [r["oos_return_pct"] for r in rows if r["oos_return_pct"] is not None]
    if oos_vals:
        print(f"  Mean OOS return: {sum(oos_vals)/len(oos_vals):.2f}%")
        print(f"  Median OOS return: {sorted(oos_vals)[len(oos_vals)//2]:.2f}%")
        print(f"  Best:  {max(oos_vals):.2f}%")
        print(f"  Worst: {min(oos_vals):.2f}%")

    # Most frequent indicators in #1 positions
    ind_counter = Counter()
    for r in rows:
        il = r.get("indicator_list", "")
        if il:
            # indicators are comma-separated
            for ind in il.split(","):
                ind = ind.strip()
                if ind:
                    ind_counter[ind] += 1
    print(f"\n--- Most Frequent Indicators in #1 Strategies (top 15) ---")
    for ind, cnt in ind_counter.most_common(15):
        print(f"  {ind:<40} : {cnt} ({100*cnt/len(rows):.0f}%)")

    # Full indicator_list combos
    combo_counter = Counter(r.get("indicator_list", "") for r in rows)
    print(f"\n--- Most Frequent Indicator Combos (top 10) ---")
    for combo, cnt in combo_counter.most_common(10):
        print(f"  {combo:<55} : {cnt}")

    # Most frequent regimes
    regime_counter = Counter(r.get("regime", "") for r in rows)
    print(f"\n--- Regime Distribution ---")
    for regime, cnt in regime_counter.most_common():
        print(f"  {regime:<25} : {cnt} ({100*cnt/len(rows):.0f}%)")

    # Composite score distribution (for runs that have it)
    comp_vals = [r["composite_score"] for r in rows if r["composite_score"] is not None]
    if comp_vals:
        print(f"\n--- Composite Score (n={len(comp_vals)}) ---")
        print(f"  Mean:   {sum(comp_vals)/len(comp_vals):.4f}")
        print(f"  Median: {sorted(comp_vals)[len(comp_vals)//2]:.4f}")
        print(f"  Best:   {max(comp_vals):.4f}")
        print(f"  Worst:  {min(comp_vals):.4f}")

    # tp/sl/max_hold distribution
    print(f"\n--- TP/SL/MaxHold Distribution ---")
    for field, label in [("tp", "TP Stop"), ("sl", "SL Stop"), ("max_hold", "Max Hold")]:
        vals = Counter(r[field] for r in rows if r[field])
        print(f"  {label}:")
        for v, cnt in vals.most_common(8):
            print(f"    {v:<10}: {cnt}")

    print(f"\nDone. Processed {len(rows)} runs.")


if __name__ == "__main__":
    main()
