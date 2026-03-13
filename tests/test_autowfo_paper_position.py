import json

from autowfo.paper_position import PaperPositionStore


def test_open_close_roundtrip_pnl(tmp_path):
    path = tmp_path / "artifacts" / "paper_positions.json"
    store = PaperPositionStore(path)

    opened = store.open_position(
        signal_id="sig_001",
        experiment_id="exp_001",
        open_price=100.0,
        open_ts="2026-03-01T00:00:00Z",
    )
    assert opened["status"] == "open"
    assert opened["pnl_pct"] is None

    pnl_pct, closed = store.close_position(
        signal_id="sig_001",
        close_price=110.0,
        close_ts="2026-03-01T01:00:00Z",
    )
    assert round(pnl_pct, 8) == 10.0
    assert closed["status"] == "closed"
    assert closed["close_price"] == 110.0
    assert closed["pnl_pct"] == pnl_pct


def test_positions_json_schema_and_persistence(tmp_path):
    path = tmp_path / "artifacts" / "paper_positions.json"
    store = PaperPositionStore(path)
    store.open_position(
        signal_id="sig_002",
        experiment_id="exp_002",
        open_price=50.0,
        open_ts="2026-03-01T00:00:00Z",
    )

    rows = store.list_positions()
    assert len(rows) == 1
    assert set(rows[0].keys()) == {
        "signal_id",
        "experiment_id",
        "open_ts",
        "open_price",
        "close_ts",
        "close_price",
        "pnl_pct",
        "status",
    }

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[0]["signal_id"] == "sig_002"
    assert not (path.parent / "paper_positions.json.tmp").exists()


def test_open_position_rejects_duplicate_open_signal(tmp_path):
    path = tmp_path / "artifacts" / "paper_positions.json"
    store = PaperPositionStore(path)
    store.open_position(
        signal_id="sig_dup",
        experiment_id="exp_dup",
        open_price=10.0,
        open_ts="2026-03-01T00:00:00Z",
    )

    try:
        store.open_position(
            signal_id="sig_dup",
            experiment_id="exp_dup",
            open_price=11.0,
            open_ts="2026-03-01T00:05:00Z",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "already open"


def test_close_position_without_open_raises(tmp_path):
    path = tmp_path / "artifacts" / "paper_positions.json"
    store = PaperPositionStore(path)
    try:
        store.close_position(
            signal_id="sig_none",
            close_price=10.0,
            close_ts="2026-03-01T01:00:00Z",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "no open position"


def test_open_position_allows_multiple_strategies_in_parallel(tmp_path):
    path = tmp_path / "artifacts" / "paper_positions.json"
    store = PaperPositionStore(path)
    first = store.open_position(
        signal_id="sig_parallel_1",
        experiment_id="exp_parallel_1",
        open_price=100.0,
        open_ts="2026-03-01T00:00:00Z",
    )
    second = store.open_position(
        signal_id="sig_parallel_2",
        experiment_id="exp_parallel_2",
        open_price=200.0,
        open_ts="2026-03-01T00:00:00Z",
    )
    assert first["status"] == "open"
    assert second["status"] == "open"
    open_rows = store.list_open_positions()
    assert len(open_rows) == 2
    assert {row["signal_id"] for row in open_rows} == {"sig_parallel_1", "sig_parallel_2"}


def test_portfolio_snapshot_unrealized_pnl_with_latest_prices(tmp_path):
    path = tmp_path / "artifacts" / "paper_positions.json"
    store = PaperPositionStore(path)
    store.open_position(
        signal_id="sig_port_1",
        experiment_id="exp_port_1",
        open_price=100.0,
        open_ts="2026-03-01T00:00:00Z",
    )
    store.open_position(
        signal_id="sig_port_2",
        experiment_id="exp_port_2",
        open_price=100.0,
        open_ts="2026-03-01T00:00:00Z",
    )
    snapshot = store.portfolio_snapshot(latest_prices={"signals": {"sig_port_1": 120.0, "sig_port_2": 90.0}})
    assert snapshot["open_total"] == 2
    rows = {row["signal_id"]: row for row in snapshot["positions"]}
    assert round(float(rows["sig_port_1"]["unrealized_pnl_pct"]), 8) == 20.0
    assert round(float(rows["sig_port_2"]["unrealized_pnl_pct"]), 8) == -10.0
    assert round(float(snapshot["total_unrealized_pnl_pct"]), 8) == 10.0

