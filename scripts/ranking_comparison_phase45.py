"""AWF-227: Before/after ranking comparison for Phase 45.

Compares old ranking logic (no combo dedup) vs new logic (with dedup)
using a Phase 44 trusted run's combo_summary.csv.

Usage:
    python scripts/ranking_comparison_phase45.py [run_id]

Default run_id: 20260314_104729 (BNB/BTC 2h trusted rerun)
"""

import json
import sys
from pathlib import Path

import pandas as pd

# Ensure autowfo is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autowfo.ranking import (
    _build_composite_score,
    _dedup_by_combo_group,
    _resolve_ranking_config,
    _sort_by_score,
)


def _top10_summary(df: pd.DataFrame) -> list[dict]:
    cols = ["indicator_list", "regime_name", "vol_mode", "composite_score",
            "oos_avg_total_return_pct", "oos_avg_daily_trades", "tp_stop", "sl_stop", "max_hold"]
    available = [c for c in cols if c in df.columns]
    rows = []
    for _, row in df.head(10).iterrows():
        rows.append({c: _safe_val(row.get(c)) for c in available})
    return rows


def _safe_val(v):
    if pd.isna(v):
        return None
    if isinstance(v, float):
        return round(v, 6)
    return v


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else "20260314_104729"
    artifacts = Path("artifacts")
    combo_path = artifacts / "runs" / run_id / "results" / "param_sweep_combo_summary.csv"

    if not combo_path.exists():
        print(f"[error] combo_summary not found: {combo_path}")
        sys.exit(1)

    print(f"[info] reading {combo_path}")
    df = pd.read_csv(combo_path, low_memory=False)
    print(f"[info] total combos: {len(df)}")

    ranking_config = _resolve_ranking_config(None)

    # --- Old logic: sort + head(10), no dedup ---
    old_sorted, score_col = _sort_by_score(df, tie_break_avg_hold=True, ranking_config=ranking_config)
    old_top10 = old_sorted.head(10)
    old_unique = old_top10["indicator_list"].nunique() if "indicator_list" in old_top10.columns else "N/A"

    # --- New logic: sort + dedup + head(10) ---
    new_sorted, _ = _sort_by_score(df, tie_break_avg_hold=True, ranking_config=ranking_config)
    new_deduped = _dedup_by_combo_group(new_sorted, ranking_config=ranking_config)
    new_top10 = new_deduped.head(10)
    new_unique = new_top10["indicator_list"].nunique() if "indicator_list" in new_top10.columns else "N/A"

    result = {
        "run_id": run_id,
        "total_combos": len(df),
        "old_logic": {
            "description": "sort_by_score + head(10), no combo dedup",
            "unique_indicator_combos": int(old_unique) if isinstance(old_unique, (int, float)) else old_unique,
            "top10": _top10_summary(old_top10),
        },
        "new_logic": {
            "description": "sort_by_score + dedup_by_combo_group + head(10)",
            "unique_indicator_combos": int(new_unique) if isinstance(new_unique, (int, float)) else new_unique,
            "top10": _top10_summary(new_top10),
        },
        "improvement": {
            "unique_combos_old": int(old_unique) if isinstance(old_unique, (int, float)) else old_unique,
            "unique_combos_new": int(new_unique) if isinstance(new_unique, (int, float)) else new_unique,
            "diversity_improved": (
                new_unique > old_unique
                if isinstance(old_unique, (int, float)) and isinstance(new_unique, (int, float))
                else None
            ),
        },
    }

    out_path = Path("plans") / "ranking_comparison_phase45.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[result] old top10 unique combos: {old_unique}")
    print(f"[result] new top10 unique combos: {new_unique}")
    print(f"[output] {out_path}")


if __name__ == "__main__":
    main()
