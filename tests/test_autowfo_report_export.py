from pathlib import Path

from scripts.autowfo.report_export import export_html_report


class _DummyAnalyticsStore:
    def query_indicator_leaderboard(self, limit=10):
        _ = limit
        return [
            {
                "trigger_indicators": '["RSI"]',
                "action_indicators": '["BB"]',
                "avg_sharpe": 1.25,
                "avg_win_rate": 0.57,
                "n_combos": 12,
                "n_experiments": 3,
                "paper_avg_pnl": 2.5,
            },
            {
                "trigger_indicators": '["MACD"]',
                "action_indicators": '["EMA"]',
                "avg_sharpe": 0.9,
                "avg_win_rate": 0.51,
                "n_combos": 8,
                "n_experiments": 2,
                "paper_avg_pnl": None,
            },
        ]

    def query_experiment_comparison(self):
        return [
            {
                "experiment_id": "exp_a",
                "avg_oos_sharpe": 1.1,
                "avg_oos_win_rate": 0.55,
                "total_combos": 40,
                "total_runs": 3,
                "best_wf_score": 0.91,
            }
        ]


def test_export_html_report_contains_required_sections(tmp_path):
    out_path = tmp_path / "artifacts" / "research_report.html"
    payload = export_html_report(_DummyAnalyticsStore(), out_path)

    assert payload["ok"] is True
    assert payload["output_path"] == str(out_path)
    assert out_path.exists()

    html = out_path.read_text(encoding="utf-8")
    assert "AUTOWFO Research Report" in html
    assert "Indicator Leaderboard (Top 10)" in html
    assert "Cross-Experiment Sharpe Comparison" in html
    assert "Paper Portfolio Summary" in html
    assert "<table>" in html
    assert "trigger_indicators" in html
    assert "avg_oos_sharpe" in html
    assert "Generated UTC:" in html
