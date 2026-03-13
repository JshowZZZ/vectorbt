import sqlite3

from autowfo.artifact_store import ArtifactStore
from autowfo.storage_contract import RUN_META_SCHEMA_VERSION


def _insert_combo_row(conn, *, combo_id, experiment_id, run_id, wf_score, oos_sharpe):
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
            "{}",
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


def test_init_run_creates_expected_directory(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_dir = store.init_run("20260301_020000")
    expected = tmp_path / "artifacts" / "experiments" / "exp_demo" / "runs" / "20260301_020000"
    assert run_dir == expected
    assert run_dir.exists()
    assert run_dir.is_dir()


def test_init_run_idempotent(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_a = store.init_run("20260301_020000")
    run_b = store.init_run("20260301_020000")
    assert run_a == run_b
    assert run_a.exists()


def test_init_results_db_creates_wal_and_schema(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    conn = store.init_results_db("20260301_020000")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"

        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(combo_results)").fetchall()
        ]
        assert columns == [
            "combo_id",
            "experiment_id",
            "run_id",
            "direction",
            "trigger_asset",
            "action_asset",
            "indicator_params",
            "condition_params",
            "risk_params",
            "oos_sharpe",
            "oos_win_rate",
            "oos_n_trades",
            "oos_total_return",
            "wf_score",
            "created_utc",
        ]
    finally:
        conn.close()


def test_init_results_db_idempotent(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    conn1 = store.init_results_db("20260301_020000")
    conn1.close()
    conn2 = store.init_results_db("20260301_020000")
    try:
        table_rows = conn2.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='combo_results'"
        ).fetchone()[0]
        idx_rows = conn2.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name IN ('idx_experiment', 'idx_wf_score')"
        ).fetchone()[0]
        assert table_rows == 1
        assert idx_rows == 2
    finally:
        conn2.close()


def test_run_meta_roundtrip(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_id = "20260301_020000"
    payload = {"run_id": run_id, "n_combos": 42}
    store.write_run_meta(run_id, payload)
    loaded = store.read_run_meta(run_id)
    assert loaded["run_id"] == run_id
    assert loaded["n_combos"] == 42
    assert loaded["schema_version"] == RUN_META_SCHEMA_VERSION


def test_read_run_meta_legacy_payload_injects_schema_version(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_id = "20260301_020000"
    meta_path = store.init_run(run_id) / "run_meta.json"
    meta_path.write_text('{"run_id":"20260301_020000","n_combos":7}', encoding="utf-8")

    loaded = store.read_run_meta(run_id)

    assert loaded["run_id"] == run_id
    assert loaded["n_combos"] == 7
    assert loaded["schema_version"] == RUN_META_SCHEMA_VERSION


def test_read_run_meta_missing_raises(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    try:
        store.read_run_meta("20260301_020000")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_list_runs_sorted(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    store.init_run("20260302_010000")
    store.init_run("20260301_020000")
    store.init_run("20260303_030000")
    assert store.list_runs() == ["20260301_020000", "20260302_010000", "20260303_030000"]


def test_tests_use_tmp_path_only(tmp_path):
    # Smoke assertion that this suite writes under supplied tmp_path base dir.
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    db_path = store.get_run_db_path("20260301_020000")
    store.init_run("20260301_020000")
    assert str(db_path).startswith(str(tmp_path))


def test_query_run_results_reads_from_sqlite_and_sorts_by_wf_score(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_id = "20260301_020000"
    conn = store.init_results_db(run_id)
    try:
        _insert_combo_row(
            conn,
            combo_id="combo_a",
            experiment_id="exp_demo",
            run_id=run_id,
            wf_score=0.1,
            oos_sharpe=0.3,
        )
        _insert_combo_row(
            conn,
            combo_id="combo_b",
            experiment_id="exp_demo",
            run_id=run_id,
            wf_score=0.9,
            oos_sharpe=1.2,
        )
        _insert_combo_row(
            conn,
            combo_id="combo_c",
            experiment_id="exp_demo",
            run_id=run_id,
            wf_score=0.5,
            oos_sharpe=0.8,
        )
        conn.commit()
    finally:
        conn.close()

    rows = store.query_run_results(run_id=run_id, limit=2)
    assert len(rows) == 2
    assert rows[0]["combo_id"] == "combo_b"
    assert rows[1]["combo_id"] == "combo_c"
    assert set(rows[0].keys()) >= {
        "combo_id",
        "direction",
        "indicator_params",
        "condition_params",
        "risk_params",
        "oos_sharpe",
        "oos_win_rate",
        "oos_n_trades",
        "wf_score",
    }


def test_query_run_results_missing_run_raises(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    try:
        store.query_run_results(run_id="does_not_exist")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_query_experiment_summary_aggregates_across_runs(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_a = "20260301_020000"
    run_b = "20260302_030000"

    store.write_run_meta(run_a, {"run_id": run_a, "n_combos": 2, "best_oos_sharpe": 1.1})
    store.write_run_meta(run_b, {"run_id": run_b, "n_combos": 1, "best_oos_sharpe": 2.3})

    summary = store.query_experiment_summary()
    assert summary["experiment_id"] == "exp_demo"
    assert summary["runs_count"] == 2
    assert summary["total_combos"] == 3
    assert summary["best_oos_sharpe"] == 2.3
    assert summary["latest_run_id"] == run_b


def test_query_experiment_summary_empty_experiment(tmp_path):
    store = ArtifactStore("exp_missing", base_dir=tmp_path / "artifacts")
    summary = store.query_experiment_summary()
    assert summary == {
        "experiment_id": "exp_missing",
        "runs_count": 0,
        "total_combos": 0,
        "best_oos_sharpe": None,
        "latest_run_id": None,
    }


def test_query_all_results_returns_cross_run_top_rows(tmp_path):
    store = ArtifactStore("exp_demo", base_dir=tmp_path / "artifacts")
    run_a = "20260301_020000"
    run_b = "20260302_030000"

    conn_a = store.init_results_db(run_a)
    try:
        _insert_combo_row(
            conn_a,
            combo_id="combo_a_low",
            experiment_id="exp_demo",
            run_id=run_a,
            wf_score=0.2,
            oos_sharpe=0.4,
        )
        _insert_combo_row(
            conn_a,
            combo_id="combo_a_high",
            experiment_id="exp_demo",
            run_id=run_a,
            wf_score=0.9,
            oos_sharpe=1.9,
        )
        conn_a.commit()
    finally:
        conn_a.close()

    conn_b = store.init_results_db(run_b)
    try:
        _insert_combo_row(
            conn_b,
            combo_id="combo_b_mid",
            experiment_id="exp_demo",
            run_id=run_b,
            wf_score=0.6,
            oos_sharpe=1.2,
        )
        conn_b.commit()
    finally:
        conn_b.close()

    rows = store.query_all_results(limit=2)
    assert len(rows) == 2
    assert rows[0]["combo_id"] == "combo_a_high"
    assert rows[1]["combo_id"] == "combo_b_mid"

