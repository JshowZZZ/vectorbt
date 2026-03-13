"""Export self-contained research HTML report from analytics data."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from string import Template
from typing import Any


_HTML_TEMPLATE = Template(
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AUTOWFO Research Report</title>
  <style>
    body { font-family: "Segoe UI", Arial, sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }
    h1, h2 { margin: 0 0 12px 0; color: #0f172a; }
    .meta { margin-bottom: 20px; color: #334155; font-size: 14px; }
    .card { background: white; border: 1px solid #cbd5e1; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; }
    th, td { border: 1px solid #e2e8f0; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background: #f1f5f9; color: #0f172a; }
    .muted { color: #64748b; font-size: 13px; }
    .empty { color: #64748b; padding: 8px 0; }
    .summary-grid { display: grid; grid-template-columns: repeat(2, minmax(180px, 1fr)); gap: 10px; }
    .summary-item { border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #f8fafc; }
    .summary-label { color: #64748b; font-size: 12px; margin-bottom: 4px; }
    .summary-value { color: #0f172a; font-size: 18px; font-weight: 700; }
  </style>
</head>
<body>
  <h1>AUTOWFO Research Report</h1>
  <div class="meta">Generated UTC: $generated_utc</div>

  <div class="card">
    <h2>Indicator Leaderboard (Top 10)</h2>
    <div class="muted">Cross-run indicator effectiveness based on analytics leaderboard.</div>
    $leaderboard_table
  </div>

  <div class="card">
    <h2>Cross-Experiment Sharpe Comparison</h2>
    <div class="muted">Experiment-level OOS metrics ordered by average OOS Sharpe.</div>
    $comparison_table
  </div>

  <div class="card">
    <h2>Paper Portfolio Summary</h2>
    <div class="muted">Summary derived from analytics `paper_avg_pnl` availability in leaderboard data.</div>
    $paper_summary
  </div>
</body>
</html>
"""
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _format_number(value: Any, precision: int = 4) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.{precision}f}"


def _indicator_text(row: dict, key: str) -> str:
    raw = row.get(key)
    text = str(raw if raw is not None else "").strip()
    return text or "[]"


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<div class="empty">No data available.</div>'
    th_html = "".join(f"<th>{escape(col)}</th>" for col in headers)
    tr_html = []
    for row in rows:
        tr_html.append("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>")
    return "<table><thead><tr>" + th_html + "</tr></thead><tbody>" + "".join(tr_html) + "</tbody></table>"


def _build_leaderboard_table(leaderboard_rows: list[dict]) -> str:
    headers = [
        "trigger_indicators",
        "action_indicators",
        "avg_sharpe",
        "avg_win_rate",
        "n_combos",
        "n_experiments",
        "paper_avg_pnl",
    ]
    rows = []
    for row in leaderboard_rows[:10]:
        rows.append(
            [
                _indicator_text(row, "trigger_indicators"),
                _indicator_text(row, "action_indicators"),
                _format_number(row.get("avg_sharpe")),
                _format_number(row.get("avg_win_rate")),
                str(int(_safe_float(row.get("n_combos")) or 0)),
                str(int(_safe_float(row.get("n_experiments")) or 0)),
                _format_number(row.get("paper_avg_pnl")),
            ]
        )
    return _render_table(headers, rows)


def _build_comparison_table(comparison_rows: list[dict]) -> str:
    headers = [
        "experiment_id",
        "avg_oos_sharpe",
        "avg_oos_win_rate",
        "total_combos",
        "total_runs",
        "best_wf_score",
    ]
    rows = []
    for row in comparison_rows:
        rows.append(
            [
                str(row.get("experiment_id") or ""),
                _format_number(row.get("avg_oos_sharpe")),
                _format_number(row.get("avg_oos_win_rate")),
                str(int(_safe_float(row.get("total_combos")) or 0)),
                str(int(_safe_float(row.get("total_runs")) or 0)),
                _format_number(row.get("best_wf_score")),
            ]
        )
    return _render_table(headers, rows)


def _build_paper_summary(leaderboard_rows: list[dict]) -> str:
    pnl_values = []
    for row in leaderboard_rows:
        parsed = _safe_float(row.get("paper_avg_pnl"))
        if parsed is not None:
            pnl_values.append(parsed)

    avg_value = sum(pnl_values) / len(pnl_values) if pnl_values else None
    max_value = max(pnl_values) if pnl_values else None
    min_value = min(pnl_values) if pnl_values else None
    summary_items = [
        ("leaderboard_rows", str(len(leaderboard_rows))),
        ("rows_with_paper_pnl", str(len(pnl_values))),
        ("paper_avg_pnl_mean", _format_number(avg_value)),
        ("paper_avg_pnl_max", _format_number(max_value)),
        ("paper_avg_pnl_min", _format_number(min_value)),
    ]
    blocks = []
    for label, value in summary_items:
        blocks.append(
            '<div class="summary-item">'
            f'<div class="summary-label">{escape(label)}</div>'
            f'<div class="summary-value">{escape(value)}</div>'
            "</div>"
        )
    return '<div class="summary-grid">' + "".join(blocks) + "</div>"


def export_html_report(analytics_store, output_path: str | Path) -> dict:
    leaderboard_rows = analytics_store.query_indicator_leaderboard(limit=10)
    comparison_rows = analytics_store.query_experiment_comparison()
    generated_utc = _utc_now_iso()
    html = _HTML_TEMPLATE.substitute(
        generated_utc=escape(generated_utc),
        leaderboard_table=_build_leaderboard_table(leaderboard_rows),
        comparison_table=_build_comparison_table(comparison_rows),
        paper_summary=_build_paper_summary(leaderboard_rows),
    )
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return {
        "ok": True,
        "output_path": str(out_path),
        "generated_utc": generated_utc,
        "leaderboard_rows": len(leaderboard_rows[:10]),
        "comparison_rows": len(comparison_rows),
    }

