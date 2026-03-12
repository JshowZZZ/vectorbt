import json

import pytest

duckdb = pytest.importorskip("duckdb")

from scripts.autowfo.analytics import AnalyticsStore
from scripts.autowfo.artifact_store import ArtifactStore


def _insert_combo_row(
    conn,
    *,
    combo_id,
    experiment_id,
    run_id,
    wf_score,
    oos_sharpe,
    oos_win_rate,
    oos_n_trades,
    trigger_indicators,
    action_indicators,
):
    conn.execute(
        """
        INSERT INTO combo_results (
            combo_id, experiment_id, run_id, direction,
            trigger_asset, action_asset,
            indicator_params, condition_params, risk_params,
            oos_sharpe, oos_win_rate, oos_n_trades, oos_total_return,
            wf_score, created_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            combo_id,
            experiment_id,
            run_id,
            "long",
            "BTC/USDT",
            "ETH/USDT",
            json.dumps(
                {
                    "trigger_indicators": trigger_indicators,
                    "action_indicators": action_indicators,
                }
            ),
            "{}",
            "{}",
            oos_sharpe,
            oos_win_rate,
            oos_n_trades,
            0.1,
            wf_score,
            "2026-03-01T00:00:00+00:00",
        ),
    )


def _make_run(artifact_store, run_id, experiment_id, rows):
    conn = artifact_store.init_results_db(run_id)
    try:
        for row in rows:
            _insert_combo_row(conn, run_id=run_id, experiment_id=experiment_id, **row)
        conn.commit()
    finally:
        conn.close()


def test_update_from_run_is_idempotent(tmp_path):
    experiment_id = "exp_analytics_v1"
    store = ArtifactStore(experiment_id, base_dir=tmp_path / "artifacts")
    run_id = "20260301_020000"
    _make_run(
        store,
        run_id,
        experiment_id,
        [
            {
                "combo_id": "combo_a",
                "wf_score": 0.7,
                "oos_sharpe": 1.2,
                "oos_win_rate": 0.55,
                "oos_n_trades": 20,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["BB"],
            },
            {
                "combo_id": "combo_b",
                "wf_score": 0.9,
                "oos_sharpe": 1.8,
                "oos_win_rate": 0.61,
                "oos_n_trades": 25,
                "trigger_indicators": ["MACD"],
                "action_indicators": ["EMA"],
            },
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    inserted_first = analytics.update_from_run(experiment_id, run_id, store)
    inserted_second = analytics.update_from_run(experiment_id, run_id, store)

    conn = duckdb.connect(str(tmp_path / "analytics.duckdb"))
    try:
        total_rows = conn.execute("SELECT COUNT(*) FROM combo_results").fetchone()[0]
    finally:
        conn.close()

    assert inserted_first == 2
    assert inserted_second == 2
    assert total_rows == 2


def test_views_and_queries_return_expected_shape(tmp_path):
    experiment_id = "exp_analytics_v2"
    store = ArtifactStore(experiment_id, base_dir=tmp_path / "artifacts")
    run_id = "20260302_030000"
    _make_run(
        store,
        run_id,
        experiment_id,
        [
            {
                "combo_id": "combo_high",
                "wf_score": 0.95,
                "oos_sharpe": 2.1,
                "oos_win_rate": 0.66,
                "oos_n_trades": 30,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["BB"],
            },
            {
                "combo_id": "combo_low_trades",
                "wf_score": 0.40,
                "oos_sharpe": 0.5,
                "oos_win_rate": 0.45,
                "oos_n_trades": 5,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["Volume"],
            },
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    analytics.update_from_run(experiment_id, run_id, store)
    analytics.create_views()

    leaderboard = analytics.query_indicator_leaderboard(limit=20)
    best = analytics.query_all_time_best(limit=50)

    assert isinstance(leaderboard, list)
    assert len(leaderboard) == 1
    assert set(leaderboard[0].keys()) >= {
        "trigger_indicators",
        "action_indicators",
        "n_combos",
        "avg_win_rate",
        "avg_sharpe",
        "n_experiments",
    }
    assert isinstance(best, list)
    assert best[0]["combo_id"] == "combo_high"


def test_query_experiment_comparison(tmp_path):
    store_a = ArtifactStore("exp_a", base_dir=tmp_path / "artifacts")
    store_b = ArtifactStore("exp_b", base_dir=tmp_path / "artifacts")
    _make_run(
        store_a,
        "20260301_020000",
        "exp_a",
        [
            {
                "combo_id": "combo_a1",
                "wf_score": 0.7,
                "oos_sharpe": 1.0,
                "oos_win_rate": 0.5,
                "oos_n_trades": 12,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["BB"],
            }
        ],
    )
    _make_run(
        store_b,
        "20260301_020000",
        "exp_b",
        [
            {
                "combo_id": "combo_b1",
                "wf_score": 0.9,
                "oos_sharpe": 2.0,
                "oos_win_rate": 0.7,
                "oos_n_trades": 18,
                "trigger_indicators": ["MACD"],
                "action_indicators": ["EMA"],
            }
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    analytics.update_from_run("exp_a", "20260301_020000", store_a)
    analytics.update_from_run("exp_b", "20260301_020000", store_b)

    rows = analytics.query_experiment_comparison()
    assert len(rows) == 2
    by_id = {row["experiment_id"]: row for row in rows}
    assert by_id["exp_a"]["total_combos"] == 1
    assert by_id["exp_b"]["best_wf_score"] == 0.9


def test_query_experiment_comparison_includes_total_runs(tmp_path):
    store = ArtifactStore("exp_multi_run", base_dir=tmp_path / "artifacts")
    _make_run(
        store,
        "20260301_010000",
        "exp_multi_run",
        [
            {
                "combo_id": "combo_r1",
                "wf_score": 0.6,
                "oos_sharpe": 0.9,
                "oos_win_rate": 0.5,
                "oos_n_trades": 11,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["BB"],
            }
        ],
    )
    _make_run(
        store,
        "20260302_010000",
        "exp_multi_run",
        [
            {
                "combo_id": "combo_r2",
                "wf_score": 0.8,
                "oos_sharpe": 1.3,
                "oos_win_rate": 0.6,
                "oos_n_trades": 14,
                "trigger_indicators": ["MACD"],
                "action_indicators": ["EMA"],
            }
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    analytics.update_from_run("exp_multi_run", "20260301_010000", store)
    analytics.update_from_run("exp_multi_run", "20260302_010000", store)

    rows = analytics.query_experiment_comparison()
    assert len(rows) == 1
    row = rows[0]
    assert row["experiment_id"] == "exp_multi_run"
    assert "total_runs" in row
    assert row["total_runs"] >= 1
    assert row["total_runs"] == 2


def test_query_indicator_coverage_map(tmp_path):
    store = ArtifactStore("exp_cov", base_dir=tmp_path / "artifacts")
    _make_run(
        store,
        "20260303_010000",
        "exp_cov",
        [
            {
                "combo_id": "combo_cov_1",
                "wf_score": 0.7,
                "oos_sharpe": 1.1,
                "oos_win_rate": 0.52,
                "oos_n_trades": 12,
                "trigger_indicators": ["RSI", "MACD"],
                "action_indicators": ["BB"],
            },
            {
                "combo_id": "combo_cov_2",
                "wf_score": 0.8,
                "oos_sharpe": 1.5,
                "oos_win_rate": 0.57,
                "oos_n_trades": 14,
                "trigger_indicators": ["EMA"],
                "action_indicators": ["BB"],
            },
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    analytics.update_from_run("exp_cov", "20260303_010000", store)

    rows = analytics.query_indicator_coverage_map()
    assert rows
    assert set(rows[0].keys()) >= {"indicator_a", "indicator_b", "tested", "avg_sharpe", "total_combos"}

    by_pair = {(row["indicator_a"], row["indicator_b"]): row for row in rows}
    assert by_pair[("BB", "EMA")]["tested"] is True
    assert by_pair[("BB", "EMA")]["avg_sharpe"] is not None
    assert by_pair[("EMA", "MACD")]["tested"] is False


def test_query_analytics_growth_format(tmp_path):
    store_a = ArtifactStore("exp_growth_a", base_dir=tmp_path / "artifacts")
    store_b = ArtifactStore("exp_growth_b", base_dir=tmp_path / "artifacts")
    _make_run(
        store_a,
        "20260310_010000",
        "exp_growth_a",
        [
            {
                "combo_id": "combo_ga1",
                "wf_score": 0.6,
                "oos_sharpe": 1.0,
                "oos_win_rate": 0.51,
                "oos_n_trades": 12,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["BB"],
            }
        ],
    )
    _make_run(
        store_b,
        "20260311_010000",
        "exp_growth_b",
        [
            {
                "combo_id": "combo_gb1",
                "wf_score": 0.8,
                "oos_sharpe": 1.4,
                "oos_win_rate": 0.58,
                "oos_n_trades": 16,
                "trigger_indicators": ["MACD"],
                "action_indicators": ["EMA"],
            }
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    analytics.update_from_run("exp_growth_a", "20260310_010000", store_a)
    analytics.update_from_run("exp_growth_b", "20260311_010000", store_b)

    growth = analytics.query_analytics_growth()
    assert set(growth.keys()) == {"total_experiments", "total_runs", "total_combos", "leaderboard_size"}
    assert growth["total_experiments"] == 2
    assert growth["total_runs"] == 2
    assert growth["total_combos"] == 2
    assert growth["leaderboard_size"] >= 1


def test_add_paper_feedback_updates_leaderboard_paper_avg_pnl(tmp_path):
    store = ArtifactStore("exp_pf", base_dir=tmp_path / "artifacts")
    _make_run(
        store,
        "20260312_010000",
        "exp_pf",
        [
            {
                "combo_id": "combo_pf_1",
                "wf_score": 0.7,
                "oos_sharpe": 1.1,
                "oos_win_rate": 0.55,
                "oos_n_trades": 20,
                "trigger_indicators": ["RSI"],
                "action_indicators": ["BB"],
            }
        ],
    )

    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    analytics.update_from_run("exp_pf", "20260312_010000", store)
    assert analytics.add_paper_feedback("exp_pf", 5.0, "2026-03-01T00:00:00Z") == 1
    assert analytics.add_paper_feedback("exp_pf", -1.0, "2026-03-01T01:00:00Z") == 1
    assert analytics.add_paper_feedback("exp_pf", 100.0, "2026-03-01T01:00:00Z") == 0

    leaderboard = analytics.query_indicator_leaderboard(limit=20)
    assert leaderboard
    row = leaderboard[0]
    assert "paper_avg_pnl" in row
    assert row["paper_avg_pnl"] is not None
    assert round(float(row["paper_avg_pnl"]), 8) == 2.0
