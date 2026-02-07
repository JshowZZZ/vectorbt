import pandas as pd

from scripts.autowfo import baseline as b


def test_extract_new_run_id_from_added_top10_file():
    before = {"leaderboard.csv"}
    after = {
        "leaderboard.csv",
        "param_sweep_top10_20260207_120001.csv",
        "param_sweep_combo_summary_20260207_120001.csv",
    }
    run_id = b._extract_new_run_id(before, after)
    assert run_id == "20260207_120001"


def test_trigger_decision_two_of_three():
    df = pd.DataFrame(
        [
            {"oos_avg_max_drawdown_pct": -25, "oos_segments": 1, "oos_min_total_trades": 50},
            {"oos_avg_max_drawdown_pct": -22, "oos_segments": 1, "oos_min_total_trades": 40},
            {"oos_avg_max_drawdown_pct": -5, "oos_segments": 3, "oos_min_total_trades": 60},
            {"oos_avg_max_drawdown_pct": -4, "oos_segments": 3, "oos_min_total_trades": 70},
            {"oos_avg_max_drawdown_pct": -3, "oos_segments": 3, "oos_min_total_trades": 80},
        ]
    )
    decision = b._trigger_decision(df)
    assert decision["rules"]["D1"] is True
    assert decision["rules"]["D2"] is True
    assert decision["trigger_awf_002b_006"] is True


def test_trigger_decision_not_triggered():
    df = pd.DataFrame(
        [
            {"oos_avg_max_drawdown_pct": -8, "oos_segments": 3, "oos_min_total_trades": 80},
            {"oos_avg_max_drawdown_pct": -7, "oos_segments": 3, "oos_min_total_trades": 70},
            {"oos_avg_max_drawdown_pct": -6, "oos_segments": 3, "oos_min_total_trades": 60},
            {"oos_avg_max_drawdown_pct": -5, "oos_segments": 2, "oos_min_total_trades": 50},
            {"oos_avg_max_drawdown_pct": -4, "oos_segments": 2, "oos_min_total_trades": 40},
        ]
    )
    decision = b._trigger_decision(df)
    assert decision["rules"]["D1"] is False
    assert decision["rules"]["D2"] is False
    assert decision["rules"]["D3"] is False
    assert decision["trigger_awf_002b_006"] is False


def test_comparison_summary_deltas():
    combo = {
        "rows": 10,
        "avg_oos_return_pct": 5.0,
        "avg_oos_drawdown_pct": -12.0,
        "avg_oos_min_total_trades": 35.0,
        "avg_oos_segments": 2.0,
    }
    refine = {
        "rows": 10,
        "avg_oos_return_pct": 6.5,
        "avg_oos_drawdown_pct": -10.0,
        "avg_oos_min_total_trades": 40.0,
        "avg_oos_segments": 3.0,
    }
    summary = b._comparison_summary(combo, refine)
    assert summary["delta_avg_oos_return_pct"] == 1.5
    assert summary["delta_avg_oos_drawdown_pct"] == 2.0
    assert summary["delta_avg_oos_min_total_trades"] == 5.0
    assert summary["delta_avg_oos_segments"] == 1.0


def test_copy_run_outputs_copies_current_run_and_latest_report_only(tmp_path):
    artifacts = tmp_path / "artifacts"
    target = tmp_path / "out"
    artifacts.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)

    # static
    (artifacts / "param_sweep_combo_summary.csv").write_text("x\n1\n", encoding="utf-8")
    (artifacts / "param_sweep_symbol_summary.csv").write_text("x\n1\n", encoding="utf-8")
    (artifacts / "leaderboard.csv").write_text("x\n1\n", encoding="utf-8")
    (artifacts / "results.db").write_text("db", encoding="utf-8")
    (artifacts / "run_status.json").write_text("{}", encoding="utf-8")
    (artifacts / "run_status.html").write_text("<html></html>", encoding="utf-8")

    run_id = "20260207_120001"
    # run-specific
    (artifacts / f"param_sweep_combo_summary_{run_id}.csv").write_text("x\n1\n", encoding="utf-8")
    (artifacts / f"param_sweep_symbol_summary_{run_id}.csv").write_text("x\n1\n", encoding="utf-8")
    (artifacts / f"param_sweep_top10_{run_id}.csv").write_text("x\n1\n", encoding="utf-8")

    # reports
    (artifacts / f"btc_regime_ETH-BTC_{run_id}.html").write_text("run", encoding="utf-8")
    (artifacts / "btc_regime_ETH-BTC_20260101_000001.html").write_text("old", encoding="utf-8")
    (artifacts / "btc_regime_ETH-BTC.html").write_text("latest", encoding="utf-8")

    copied = b._copy_run_outputs(artifacts, target, run_id)
    reports = sorted(copied["reports"])
    assert reports == sorted([f"btc_regime_ETH-BTC_{run_id}.html", "btc_regime_ETH-BTC.html"])
