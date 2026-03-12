import json
from datetime import datetime

import pytest

pytest.importorskip("duckdb")

from scripts.autowfo.analytics import AnalyticsStore
from scripts.autowfo.artifact_store import ArtifactStore
from scripts.autowfo.signal_exporter import export_top_signal_config


def _insert_combo_row(
    conn,
    *,
    combo_id,
    experiment_id,
    run_id,
    wf_score,
    oos_sharpe,
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
            0.5,
            10,
            0.1,
            wf_score,
            "2026-03-01T00:00:00+00:00",
        ),
    )


def test_export_top_signal_config_outputs_top1_schema(tmp_path):
    experiment_id = "exp_signal_export"
    run_id = "20260301_010000"
    artifacts = tmp_path / "artifacts"
    store = ArtifactStore(experiment_id, base_dir=artifacts)
    conn = store.init_results_db(run_id)
    try:
        _insert_combo_row(
            conn,
            combo_id="combo_low",
            experiment_id=experiment_id,
            run_id=run_id,
            wf_score=0.3,
            oos_sharpe=0.7,
            trigger_indicators=["RSI"],
            action_indicators=["BB"],
        )
        _insert_combo_row(
            conn,
            combo_id="combo_high",
            experiment_id=experiment_id,
            run_id=run_id,
            wf_score=0.9,
            oos_sharpe=1.6,
            trigger_indicators=["MACD"],
            action_indicators=["EMA"],
        )
        conn.commit()
    finally:
        conn.close()

    analytics = AnalyticsStore(artifacts / "analytics.duckdb")
    analytics.update_from_run(experiment_id, run_id, store)

    out_path = artifacts / "live_signal_config.json"
    payload = export_top_signal_config(analytics_store=analytics, top_n=5, out_path=out_path)

    assert out_path.exists()
    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved == payload
    assert set(payload.keys()) == {"experiment_id", "trigger_indicator", "action_indicator", "wf_params", "export_ts"}
    assert payload["experiment_id"] == experiment_id
    assert payload["trigger_indicator"] == "MACD"
    assert payload["action_indicator"] == "EMA"
    assert payload["wf_params"]["wf_score"] == 0.9
    datetime.fromisoformat(str(payload["export_ts"]).replace("Z", "+00:00"))


def test_export_top_signal_config_raises_when_analytics_empty(tmp_path):
    analytics = AnalyticsStore(tmp_path / "analytics.duckdb")
    with pytest.raises(ValueError, match="no analytics strategies"):
        export_top_signal_config(analytics_store=analytics, top_n=1, out_path=tmp_path / "live_signal_config.json")

