import json
import sqlite3

import pandas as pd

from autowfo import paper_dryrun_reconcile


def test_resolve_freqtrade_db_path_from_relative_sqlite_url(tmp_path):
    config_path = tmp_path / "user_data" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    resolved = paper_dryrun_reconcile.resolve_freqtrade_db_path(
        freqtrade_config_path=config_path,
        freqtrade_config={"db_url": "sqlite:///tradesv3.dryrun.sqlite"},
    )

    assert resolved == (tmp_path / "tradesv3.dryrun.sqlite").resolve()


def test_build_daily_reconcile_summary_matches_entry_and_exit_signals(tmp_path):
    trades_df = pd.DataFrame(
        [
            {
                "id": 7,
                "pair": "LTC/USDT:USDT",
                "is_open": False,
                "is_short": False,
                "open_rate": 100.0,
                "close_rate": 105.0,
                "open_date": pd.Timestamp("2026-04-13T10:00:05"),
                "close_date": pd.Timestamp("2026-04-13T12:00:03"),
                "close_profit": 0.05,
                "close_profit_abs": 5.0,
                "stake_amount": 100.0,
                "enter_tag": "autowfo-long",
                "exit_reason": "exit_signal",
            }
        ]
    )
    signal_df = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-04-13T08:00:00"),
                "pair": "LTC/BTC",
                "enter_long": 0,
                "enter_short": 0,
                "exit_long": 0,
                "exit_short": 0,
                "signal_long": 1,
                "signal_short": 0,
            },
            {
                "date": pd.Timestamp("2026-04-13T10:00:00"),
                "pair": "LTC/BTC",
                "enter_long": 1,
                "enter_short": 0,
                "exit_long": 0,
                "exit_short": 0,
                "signal_long": 0,
                "signal_short": 0,
            },
            {
                "date": pd.Timestamp("2026-04-13T12:00:00"),
                "pair": "LTC/BTC",
                "enter_long": 0,
                "enter_short": 0,
                "exit_long": 1,
                "exit_short": 0,
                "signal_long": 0,
                "signal_short": 0,
            },
        ]
    )
    live_manifest = {
        "source": {"timeframe": "2h"},
        "analysis": {"main_run_id": "run_001"},
        "runtime": {"tail_bars_per_pair": 6},
        "source_bundle_manifest": str(tmp_path / "signal_manifest.json"),
    }

    summary = paper_dryrun_reconcile.build_daily_reconcile_summary(
        trades_df,
        signal_df,
        day_start=pd.Timestamp("2026-04-13T00:00:00"),
        day_end=pd.Timestamp("2026-04-14T00:00:00"),
        pair_mapping={"LTC/BTC": "LTC/USDT:USDT"},
        live_manifest=live_manifest,
        db_path=tmp_path / "tradesv3.dryrun.sqlite",
    )

    assert summary["totals"]["opened_trades_day"] == 1
    assert summary["totals"]["closed_trades_day"] == 1
    assert summary["totals"]["entry_signal_match_count"] == 1
    assert summary["totals"]["exit_signal_match_count"] == 1
    assert summary["opened_trades"][0]["source_pair"] == "LTC/BTC"
    assert summary["opened_trades"][0]["signal_bar_utc"] == "2026-04-13T08:00:00"
    assert summary["closed_trades"][0]["signal_bar_utc"] == "2026-04-13T10:00:00"
    assert summary["closed_trades"][0]["expected_action"] == "ft_signal_exit_long"


def test_reconcile_dryrun_day_writes_summary_artifact(tmp_path, monkeypatch):
    live_manifest_path = tmp_path / "live_manifest.json"
    source_bundle_path = tmp_path / "signal_manifest.json"
    config_path = tmp_path / "freqtrade" / "user_data" / "config_autowfo_dryrun.json"
    db_path = tmp_path / "freqtrade" / "tradesv3.dryrun.sqlite"
    config_path.parent.mkdir(parents=True)
    live_manifest_path.write_text(
        json.dumps({"source_bundle_manifest": str(source_bundle_path), "source": {"timeframe": "2h"}}),
        encoding="utf-8",
    )
    source_bundle_path.write_text(json.dumps({"analysis": {"selected_row": {}}, "source": {"run_root": str(tmp_path / 'run')}}), encoding="utf-8")
    config_path.write_text(json.dumps({"autowfo_pair_mapping": {"LTC/BTC": "LTC/USDT:USDT"}}), encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER,
                pair TEXT,
                is_open BOOLEAN,
                open_rate FLOAT,
                close_rate FLOAT,
                open_date TEXT,
                close_date TEXT,
                close_profit FLOAT,
                close_profit_abs FLOAT,
                stake_amount FLOAT,
                amount FLOAT,
                exit_reason TEXT,
                strategy TEXT,
                enter_tag TEXT,
                timeframe INTEGER,
                trading_mode TEXT,
                leverage FLOAT,
                is_short BOOLEAN,
                fee_open_cost FLOAT,
                fee_close_cost FLOAT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO trades VALUES (
                1, 'LTC/USDT:USDT', 0, 100, 101,
                '2026-04-13T10:00:00+00:00', '2026-04-13T12:00:00+00:00',
                0.01, 1.0, 100, 1, 'exit_signal', 'AutowfoLiveSignalStrategyLongShort',
                'autowfo-long', 120, 'futures', 1, 0, 0.0, 0.0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        paper_dryrun_reconcile,
        "load_reconcile_signal_frame",
        lambda live_manifest, cwd=None: pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-04-13T08:00:00"),
                    "pair": "LTC/BTC",
                    "enter_long": 0,
                    "enter_short": 0,
                    "exit_long": 0,
                    "exit_short": 0,
                    "signal_long": 1,
                    "signal_short": 0,
                },
                {
                    "date": pd.Timestamp("2026-04-13T10:00:00"),
                    "pair": "LTC/BTC",
                    "enter_long": 1,
                    "enter_short": 0,
                    "exit_long": 0,
                    "exit_short": 0,
                    "signal_long": 0,
                    "signal_short": 0,
                },
                {
                    "date": pd.Timestamp("2026-04-13T12:00:00"),
                    "pair": "LTC/BTC",
                    "enter_long": 0,
                    "enter_short": 0,
                    "exit_long": 1,
                    "exit_short": 0,
                    "signal_long": 0,
                    "signal_short": 0,
                },
            ]
        ),
    )

    out_dir = tmp_path / "artifacts" / "paper_dryrun"
    payload = paper_dryrun_reconcile.reconcile_dryrun_day(
        live_manifest_path=live_manifest_path,
        out_dir=out_dir,
        freqtrade_config_path=config_path,
        db_path=db_path,
        day_utc="2026-04-13",
    )

    out_path = out_dir / "daily_summary_20260413.json"
    assert out_path.exists()
    assert payload["totals"]["entry_signal_match_count"] == 1
    assert payload["totals"]["exit_signal_match_count"] == 1


def test_load_freqtrade_trades_opens_db_in_readonly_uri_mode(tmp_path, monkeypatch):
    import sqlite3 as _sqlite3

    db_path = tmp_path / "tradesv3.dryrun.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER,
                pair TEXT,
                is_open BOOLEAN,
                open_rate FLOAT,
                close_rate FLOAT,
                open_date TEXT,
                close_date TEXT,
                close_profit FLOAT,
                close_profit_abs FLOAT,
                stake_amount FLOAT,
                amount FLOAT,
                exit_reason TEXT,
                strategy TEXT,
                enter_tag TEXT,
                timeframe INTEGER,
                trading_mode TEXT,
                leverage FLOAT,
                is_short BOOLEAN,
                fee_open_cost FLOAT,
                fee_close_cost FLOAT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    captured = []
    real_connect = _sqlite3.connect

    def spy_connect(*args, **kwargs):
        captured.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(paper_dryrun_reconcile.sqlite3, "connect", spy_connect)
    paper_dryrun_reconcile.load_freqtrade_trades(db_path)

    assert captured, "sqlite3.connect was not called"
    first_args, first_kwargs = captured[0]
    assert first_kwargs.get("uri") is True
    assert isinstance(first_args[0], str)
    assert first_args[0].startswith("file:")
    assert "mode=ro" in first_args[0]
