"""AWF-031 ??End-to-end smoke test for the AUTOWFO pipeline.

Exercises the critical integration seams with synthetic tiny data and no
network access.  The goal is to catch pipeline-breaking regressions
automatically rather than relying on manual real-data runs.

Integration seams tested:
  1. Data ??Context: synthetic OHLCV ??``_prepare_timeframe_context`` ??real
     VBT indicator precomputation
  2. Context ??Walk-Forward: ``_build_walk_forward_windows`` ??6-tuple windows
  3. Evaluation: ``evaluate_combo_task`` ??result dict with metrics
  4. Finalize artifacts: result DataFrames ??``_run_finalize_pipeline`` ??
     CSV/HTML/JSON output files
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

_N_BARS = 200  # enough for indicator lookbacks + walk-forward windows


def _make_ohlcv(index, base=100.0, noise_pct=0.01):
    """Generate a synthetic OHLCV DataFrame with slight noise."""
    rng = np.random.RandomState(42)
    close = pd.Series(
        base + np.cumsum(rng.randn(len(index)) * base * noise_pct), index=index
    )
    return pd.DataFrame(
        {
            "Open": close.shift(1).bfill(),
            "High": close * (1 + rng.uniform(0, noise_pct, len(index))),
            "Low": close * (1 - rng.uniform(0, noise_pct, len(index))),
            "Close": close,
            "Volume": 1000 + rng.randint(0, 500, len(index)).astype(float),
        },
        index=index,
    )


def _tiny_lookback_kwargs():
    """Return minimal lookback parameters to keep computation fast."""
    return dict(
        vol_lookbacks=[3],
        mom_lookbacks=[3],
        trade_mom_lookbacks=[3],
        rsi_window=3,
        bb_window=3,
        bb_alpha=2.0,
        atr_window=3,
        ma_pairs=[(3, 5)],
        obv_lookbacks=[3],
        volume_lookbacks=[3],
        roc_lookbacks=[3],
        cmf_lookbacks=[3],
        mfi_window=3,
        vroc_lookbacks=[3],
        ad_lookbacks=[3],
        cci_lookbacks=[3],
        willr_lookbacks=[3],
        adx_lookbacks=[3],
        trix_lookbacks=[3],
        dpo_lookbacks=[3],
        efi_lookbacks=[3],
        vwma_lookbacks=[3],
        ultosc_periods=(3, 5, 7),
        keltner_lookbacks=[3],
        donchian_lookbacks=[3],
        ppo_fast=3,
        ppo_slow=5,
        ppo_signal=3,
        chop_lookbacks=[3],
    )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_index():
    return pd.date_range("2024-01-01", periods=_N_BARS, freq="h")


@pytest.fixture()
def synthetic_loader(synthetic_index):
    """Return a callable that mimics ``_load_or_update_symbol``."""
    base_df = _make_ohlcv(synthetic_index, base=40000.0)
    trade_df = _make_ohlcv(synthetic_index, base=3000.0, noise_pct=0.015)

    def _loader(symbol, *_args, **_kwargs):
        return base_df if "BTC" in symbol else trade_df

    return _loader


@pytest.fixture()
def ctx(synthetic_loader, tmp_path):
    """Build a real timeframe context from synthetic data."""
    from autowfo.data import _prepare_timeframe_context

    return _prepare_timeframe_context(
        timeframe="1h",
        data_days=10,
        base_symbol="BTC/USDT",
        trade_symbols=["ETH/USDT"],
        exchange="binance",
        cache_dir=str(tmp_path / "cache"),
        cache_format="csv",
        init_cash_usdt=1000,
        capital_mode="shared",
        load_or_update_symbol_fn=synthetic_loader,
        **_tiny_lookback_kwargs(),
    )


# ===================================================================
# Seam 1: Data ??Context (real VBT indicator computation)
# ===================================================================

class TestDataToContext:
    """Verify ``_prepare_timeframe_context`` produces a complete context dict
    with all indicator maps populated from real VBT computations."""

    EXPECTED_KEYS = [
        "timeframe", "data_days", "trade_symbols", "trade_close",
        "btc_close", "btc_high", "btc_low", "btc_volume",
        "total_days", "init_cash_btc",
        "vol_zscore_by_lb", "mom_by_lb", "trade_mom_by_lb",
        "rsi_series", "bb_width", "bb_upper", "bb_lower", "atr_ratio",
        "ma_trend_by_pair", "macd_hist_ratio_series", "stoch_k",
        "obv_roc_by_lb", "volume_zscore_by_lb", "roc_by_lb",
        "cmf_by_window", "mfi_by_window",
        "vroc_by_lb", "ad_roc_by_lb",
        "cci_by_lb", "willr_by_lb", "adx_by_lb", "trix_by_lb",
        "dpo_by_lb", "efi_by_lb", "vwma_trend_by_lb",
        "ultosc_series", "keltner_pos_by_lb", "donchian_pos_by_lb",
        "ppo_hist_series", "chop_by_lb",
        "data_range",
    ]

    def test_context_has_all_keys(self, ctx):
        for key in self.EXPECTED_KEYS:
            assert key in ctx, f"Missing context key: {key}"

    def test_context_trade_close_shape(self, ctx):
        assert ctx["trade_close"].shape[0] > 0
        assert ctx["trade_close"].shape[1] >= 1  # at least 1 trade symbol

    def test_context_btc_close_not_empty(self, ctx):
        assert not ctx["btc_close"].empty

    def test_context_indicator_maps_populated(self, ctx):
        """Indicator lookback maps should have their requested keys."""
        assert 3 in ctx["vol_zscore_by_lb"]
        assert 3 in ctx["mom_by_lb"]
        assert 3 in ctx["trade_mom_by_lb"]
        assert (3, 5) in ctx["ma_trend_by_pair"]
        assert 3 in ctx["cci_by_lb"]
        assert 3 in ctx["willr_by_lb"]
        assert 3 in ctx["donchian_pos_by_lb"]

    def test_context_total_days_positive(self, ctx):
        assert ctx["total_days"] >= 1

    def test_context_init_cash_positive(self, ctx):
        assert ctx["init_cash_btc"] > 0


# ===================================================================
# Seam 2: Context ??Walk-Forward Windows
# ===================================================================

class TestWalkForwardWindows:
    """Verify ``_build_walk_forward_windows`` produces valid 6-tuple windows
    from the context."""

    def test_windows_from_context(self, ctx):
        from autowfo.split import _build_walk_forward_windows

        windows = _build_walk_forward_windows(
            index=ctx["trade_close"].index,
            train_days=3,
            test_days=1,
            step_days=1,
            valid_days=0,
            mode="anchored",
        )
        assert len(windows) >= 1, "Should have at least 1 walk-forward window"
        # Each window should be a 6-tuple
        for w in windows:
            assert len(w) == 6, f"Expected 6-tuple, got {len(w)}-tuple"
            train_start, train_end, valid_start, valid_end, test_start, test_end = w
            assert train_start < train_end
            assert test_start < test_end
            assert train_end <= test_start

    def test_windows_with_validation(self, ctx):
        from autowfo.split import _build_walk_forward_windows

        windows = _build_walk_forward_windows(
            index=ctx["trade_close"].index,
            train_days=2,
            test_days=1,
            step_days=1,
            valid_days=1,
            mode="anchored",
        )
        assert len(windows) >= 1
        for w in windows:
            train_start, train_end, valid_start, valid_end, test_start, test_end = w
            # With valid_days > 0, validation segment should exist
            assert valid_start < valid_end
            assert valid_end <= test_start


# ===================================================================
# Seam 3: Evaluation smoke (monkeypatched portfolio for speed)
# ===================================================================

class TestEvaluationSmoke:
    """Verify ``evaluate_combo_task`` produces a result dict with expected
    metrics when given a valid context and task."""

    def test_evaluate_produces_result(self, ctx, monkeypatch):
        from autowfo import evaluator as ev
        from autowfo.split import _build_walk_forward_slices

        # Build minimal slices from context
        slices = _build_walk_forward_slices(
            ctx["trade_close"].index, train_days=3, test_days=1, step_days=1
        )

        true_mask = pd.Series(True, index=ctx["trade_close"].index)

        # Monkeypatch heavy VBT operations for speed
        monkeypatch.setattr(
            ev.autowfo_engine, "_resolve_regime_signals",
            lambda **kwargs: (true_mask, true_mask, None, None),
        )
        monkeypatch.setattr(
            ev.autowfo_engine, "_build_trade_mom_filters",
            lambda trade_mom: (trade_mom > -1e9, trade_mom < 1e9),
        )
        monkeypatch.setattr(
            ev.autowfo_engine, "_compute_effective_costs",
            lambda **kwargs: (0.001, 0.001),
        )

        # Mock portfolio run to return a simple series
        def _fake_run_pf(*args, **kwargs):
            n = len(ctx["trade_close"])
            return pd.DataFrame({"value": np.linspace(100, 110, n)})

        monkeypatch.setattr(ev.autowfo_portfolio, "_run_pf", _fake_run_pf)

        # Mock metrics to return a dict of pd.Series (one entry per symbol)
        symbols = list(ctx["trade_close"].columns)

        def _fake_calc_pf_series(*args, **kwargs):
            return {
                "total_return_pct": pd.Series([10.0] * len(symbols), index=symbols),
                "total_profit": pd.Series([10.0] * len(symbols), index=symbols),
                "total_trades": pd.Series([5] * len(symbols), index=symbols),
                "win_rate_pct": pd.Series([60.0] * len(symbols), index=symbols),
                "avg_trade_pct": pd.Series([2.0] * len(symbols), index=symbols),
                "max_drawdown_pct": pd.Series([5.0] * len(symbols), index=symbols),
                "position_coverage_pct": pd.Series([50.0] * len(symbols), index=symbols),
                "avg_hold_hours": pd.Series([4.0] * len(symbols), index=symbols),
                "avg_daily_trades": pd.Series([1.0] * len(symbols), index=symbols),
            }

        monkeypatch.setattr(ev.autowfo_metrics, "_calc_pf_series", _fake_calc_pf_series)

        # Mock combo metrics for shared mode
        def _fake_calc_pf_combo_metrics(*args, **kwargs):
            return {
                "total_return_pct": 10.0,
                "total_profit": 10.0,
                "total_trades": 5,
                "win_rate_pct": 60.0,
                "avg_trade_pct": 2.0,
                "max_drawdown_pct": 5.0,
                "position_coverage_pct": 50.0,
                "avg_hold_hours": 4.0,
            }

        monkeypatch.setattr(ev.autowfo_metrics, "_calc_pf_combo_metrics", _fake_calc_pf_combo_metrics)

        # Mock coerce/apply to pass through
        monkeypatch.setattr(
            ev.autowfo_strategy, "_coerce_indicator_params",
            lambda combo_keys, combo_params, ctx: combo_params,
        )
        monkeypatch.setattr(
            ev.autowfo_strategy, "_apply_indicator_combo",
            lambda long_regime, short_regime, combo_keys, combo_params, combo_ctx: (
                true_mask, true_mask, combo_params
            ),
        )
        monkeypatch.setattr(
            ev.autowfo_strategy, "_pick_series_from_map",
            lambda key, ctx, lookback=None, default=None: default,
        )

        task = {
            "regime": {
                "regime_name": "trend_high",
                "regime_type": "trend",
                "vol_mode": "high",
                "rsi_pair": None,
            },
            "indicator_combo": ("volume_z",),
            "combo_params": {"volume_lookback": 3, "volume_z": 0.2},
            "vol_lookback": 3,
            "vol_z": 0.1,
            "mom_lookback": 3,
            "trade_mom_lookback": 3,
            "tp_stop": 0.003,
            "sl_stop": 0.006,
            "max_hold": 2,
            "filter_name": "vol_mom_volume",
            "indicator_list": "volume_z",
        }

        runtime = {
            "ctx": ctx,
            "trade_symbols_tf": list(ctx["trade_close"].columns),
            "timeframe": "1h",
            "data_days": 10,
            "exchange": "binance",
            "base_symbol": "BTC/USDT",
            "capital_mode": "shared",
            "fees": 0.001,
            "slippage_bps": 0.0,
            "spread_bps": 0.0,
            "funding_rate_daily": 0.0,
            "order_size_pct": 0.5,
            "max_concurrent_positions": 1,
            "init_cash_usdt": 1000.0,
            "wf_train_days": 3,
            "wf_test_days": 1,
            "wf_step_days": 1,
            "rsi_window": 3,
            "bar_hours": 1.0,
            "wf_slices": slices,
            "config_sha256": "test_cfg_hash",
            "data_fingerprint": "test_fp",
        }

        result = ev.evaluate_combo_task(task, runtime)

        assert result is not None
        assert "metrics_values" in result
        assert "combo_metrics" in result
        assert "oos_metrics" in result


# ===================================================================
# Seam 4: Results ??Finalize ??Artifacts
# ===================================================================

class TestFinalizeArtifacts:
    """Verify the finalize pipeline produces expected output files from
    pre-built result DataFrames."""

    def _build_synthetic_combo_df(self):
        """Build a minimal combo result DataFrame."""
        return pd.DataFrame([{
            "timeframe": "1h",
            "data_days": 10,
            "exchange": "binance",
            "base_symbol": "BTC/USDT",
            "trade_symbols_key": "ETH/USDT",
            "capital_mode": "shared",
            "fees": 0.001,
            "order_size_pct": 0.5,
            "max_concurrent_positions": 1,
            "init_cash_usdt": 1000.0,
            "wf_train_days": 3,
            "wf_test_days": 1,
            "wf_step_days": 1,
            "wf_valid_days": 0,
            "wf_mode": "anchored",
            "data_start": "2024-01-01",
            "data_end": "2024-01-09",
            "regime_name": "trend_high",
            "regime_type": "trend",
            "vol_mode": "high",
            "regime_rsi_long": None,
            "regime_rsi_short": None,
            "filter_name": "vol_mom_volume",
            "indicator_list": "volume_z",
            "indicator_count": 1,
            "vol_lookback": 3,
            "vol_z": 0.1,
            "mom_lookback": 3,
            "trade_mom_lookback": 3,
            "tp_stop": 0.003,
            "sl_stop": 0.006,
            "max_hold": 2,
            "rsi_window": 3,
            "rsi_long": None,
            "rsi_short": None,
            "bb_width": None,
            "atr_ratio": None,
            "ma_fast": None,
            "ma_slow": None,
            "macd_hist_ratio": None,
            "stoch_long": None,
            "stoch_short": None,
            "obv_lookback": None,
            "volume_lookback": 3,
            "volume_z": 0.2,
            "roc_lookback": None,
            "roc_threshold": None,
            "mfi_long": None,
            "mfi_short": None,
            "cmf_lookback": None,
            "cmf_threshold": None,
            "vroc_lookback": None,
            "vroc_threshold": None,
            "ad_lookback": None,
            "config_sha256": "test_hash",
            "data_fingerprint": "test_fp",
            "combo_seed": 42,
            "avg_total_return_pct": 5.0,
            "avg_win_rate_pct": 55.0,
            "avg_avg_trade_pct": 1.0,
            "avg_max_drawdown_pct": 3.0,
            "avg_position_coverage_pct": 40.0,
            "avg_total_trades": 10,
            "min_total_trades": 5,
            "avg_daily_trades": 1.5,
            "avg_hold_hours": 4.0,
            "sym_avg_total_return_pct": 5.0,
            "sym_avg_win_rate_pct": 55.0,
            "sym_avg_avg_trade_pct": 1.0,
            "sym_avg_max_drawdown_pct": 3.0,
            "sym_avg_position_coverage_pct": 40.0,
            "sym_avg_total_trades": 10,
            "sym_min_total_trades": 5,
            "sym_avg_daily_trades": 1.5,
            "sym_avg_hold_hours": 4.0,
            "oos_avg_total_return_pct": 3.0,
            "oos_avg_win_rate_pct": 50.0,
            "oos_avg_avg_trade_pct": 0.8,
            "oos_avg_max_drawdown_pct": 4.0,
            "oos_avg_position_coverage_pct": 35.0,
            "oos_avg_total_trades": 8,
            "oos_min_total_trades": 3,
            "oos_avg_daily_trades": 1.2,
            "oos_avg_hold_hours": 4.5,
            "oos_return_std": 2.0,
            "oos_positive_segment_ratio": 0.6,
            "oos_sharpe_like": 1.5,
            "oos_low_trade_segment_ratio": 0.1,
            "oos_low_trade_penalty": 0.0,
            "oos_segments": 3,
        }])

    def _build_synthetic_symbol_df(self):
        """Build a minimal per-symbol result DataFrame."""
        return pd.DataFrame([{
            "timeframe": "1h",
            "data_days": 10,
            "exchange": "binance",
            "base_symbol": "BTC/USDT",
            "trade_symbols_key": "ETH/USDT",
            "capital_mode": "shared",
            "fees": 0.001,
            "order_size_pct": 0.5,
            "max_concurrent_positions": 1,
            "init_cash_usdt": 1000.0,
            "wf_train_days": 3,
            "wf_test_days": 1,
            "wf_step_days": 1,
            "wf_valid_days": 0,
            "wf_mode": "anchored",
            "data_start": "2024-01-01",
            "data_end": "2024-01-09",
            "config_sha256": "test_hash",
            "data_fingerprint": "test_fp",
            "combo_seed": 42,
            "symbol": "ETH/USDT",
            "regime_name": "trend_high",
            "regime_type": "trend",
            "vol_mode": "high",
            "regime_rsi_long": None,
            "regime_rsi_short": None,
            "filter_name": "vol_mom_volume",
            "indicator_list": "volume_z",
            "indicator_count": 1,
            "vol_lookback": 3,
            "vol_z": 0.1,
            "mom_lookback": 3,
            "trade_mom_lookback": 3,
            "tp_stop": 0.003,
            "sl_stop": 0.006,
            "max_hold": 2,
            "rsi_window": 3,
            "rsi_long": None,
            "rsi_short": None,
            "bb_width": None,
            "atr_ratio": None,
            "ma_fast": None,
            "ma_slow": None,
            "macd_hist_ratio": None,
            "stoch_long": None,
            "stoch_short": None,
            "obv_lookback": None,
            "volume_lookback": 3,
            "volume_z": 0.2,
            "roc_lookback": None,
            "roc_threshold": None,
            "mfi_long": None,
            "mfi_short": None,
            "cmf_lookback": None,
            "cmf_threshold": None,
            "vroc_lookback": None,
            "vroc_threshold": None,
            "ad_lookback": None,
            "total_return_pct": 5.0,
            "total_profit": 50.0,
            "total_trades": 10,
            "win_rate_pct": 55.0,
            "avg_trade_pct": 1.0,
            "max_drawdown_pct": 3.0,
            "position_coverage_pct": 40.0,
            "avg_hold_hours": 4.0,
        }])

    def test_finalize_produces_artifacts(self, tmp_path):
        """Run the finalize pipeline on synthetic data and check output files.

        Heavy sub-functions (replay, report HTML, benchmark) are mocked so the
        test focuses on the pipeline *wiring*: snapshot writes, leaderboard
        append, metadata/registry persistence, and the ``ok: True`` contract.
        """
        from unittest.mock import patch, MagicMock

        from autowfo.engine_finalize import _run_finalize_pipeline
        from autowfo.artifacts import (
            _combine_data_fingerprints, _write_run_metadata,
        )
        from autowfo.registry import _update_run_registry
        from autowfo import constants

        out_dir = str(tmp_path / "artifacts")
        os.makedirs(out_dir, exist_ok=True)

        combo_path = os.path.join(out_dir, "param_sweep_combo_summary.csv")
        per_symbol_path = os.path.join(out_dir, "param_sweep_symbol_summary.csv")
        combo_df = self._build_synthetic_combo_df()
        symbol_df = self._build_synthetic_symbol_df()
        combo_df.to_csv(combo_path, index=False)
        symbol_df.to_csv(per_symbol_path, index=False)

        run_id = "20240101_000000"
        leaderboard_path = os.path.join(out_dir, "leaderboard.csv")
        registry_path = os.path.join(out_dir, "run_registry.json")
        run_metadata_path = os.path.join(out_dir, "run_metadata.json")
        run_metadata_path_run = os.path.join(out_dir, f"run_metadata_{run_id}.json")

        labels = {}
        for k, v in vars(constants).items():
            if isinstance(v, str) and k.startswith("LABEL_"):
                labels[k] = v

        indicator_param_fields = list(constants.INDICATOR_PARAM_FIELDS)

        timeframe_configs = [{"timeframe": "1h", "days": 10}]
        timeframe_days_map = {"1h": 10}

        # --- Mock heavy internal functions in engine_finalize namespace ---
        _mod = "autowfo.engine_finalize"

        # _fallback_activity_filter ??pass through
        mock_fallback = MagicMock(
            side_effect=lambda combo_df_current, **kw: (combo_df_current, 0.0),
        )

        # _prepare_best_timeframe_context ??fake ctx with trade_close
        _fake_idx = pd.date_range("2024-01-01", periods=50, freq="h")
        _fake_trade_close = pd.DataFrame(
            {"ETH/USDT": np.linspace(3000, 3100, 50)}, index=_fake_idx,
        )
        mock_prepare_ctx = MagicMock(
            return_value={"ctx": {"trade_close": _fake_trade_close, "trade_symbols": ["ETH/USDT"], "data_range": "2024-01-01 ??2024-01-09"}, "error": None},
        )

        # compute_bh_return_pct / compute_random_entry_return_pct
        mock_bh = MagicMock(return_value=1.5)
        mock_rand = MagicMock(return_value=0.5)

        # _prepare_best_replay_payload ??fake replay dict
        mock_replay = MagicMock(return_value={
            "trade_symbols": ["ETH/USDT"],
            "plot_symbol": "ETH/USDT",
            "data_range": "2024-01-01 ??2024-01-09",
            "scan_timeframes": "1h",
            "wf_slices": [(0, 1, 1, 1, 1, 2)],
            "best_regime": {"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
            "indicator_list": "volume_z",
            "best_indicator_combo": ("volume_z",),
            "best_filter_name": "vol_mom_volume",
            "best_params": {"volume_lookback": 3, "volume_z": 0.2},
            "best_trade_mom_lookback": 3,
            "best_tp_stop": 0.003,
            "best_sl_stop": 0.006,
            "best_max_hold": 2,
            "best_summary": pd.DataFrame([{"total_return_pct": 5.0}]),
            "plot_html": "<div>plot</div>",
        })

        # _build_best_report_frames
        mock_report_frames = MagicMock(
            return_value=(pd.DataFrame([{"param": "val"}]), pd.DataFrame([{"oos": 1}])),
        )

        # _build_report_table_html_sections
        mock_report_tables = MagicMock(return_value={
            "report_params_html": "<p>params</p>",
            "oos_summary_html": "<p>oos</p>",
            "top10_html": "<p>top10</p>",
            "summary_html": "<p>summary</p>",
        })

        # _build_report_file_paths
        mock_report_paths = MagicMock(return_value={
            "report_file_run": f"btc_regime_ETH-USDT_{run_id}.html",
            "report_path_latest": os.path.join(out_dir, "btc_regime_ETH-USDT.html"),
            "report_path_run": os.path.join(out_dir, f"btc_regime_ETH-USDT_{run_id}.html"),
        })

        # _build_report_html
        mock_html = MagicMock(return_value="<html><body>report</body></html>")

        # Leaderboard views
        mock_lb_views = MagicMock(
            return_value=(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
        )
        mock_lb_report_html = MagicMock(return_value={
            "lb_recent_html": "<p>recent</p>",
            "lb_best_html": "<p>best</p>",
        })

        patches = {
            f"{_mod}._fallback_activity_filter": mock_fallback,
            f"{_mod}._prepare_best_timeframe_context": mock_prepare_ctx,
            f"{_mod}.compute_bh_return_pct": mock_bh,
            f"{_mod}.compute_random_entry_return_pct": mock_rand,
            f"{_mod}._prepare_best_replay_payload": mock_replay,
            f"{_mod}._build_best_report_frames": mock_report_frames,
            f"{_mod}._build_report_table_html_sections": mock_report_tables,
            f"{_mod}._build_report_file_paths": mock_report_paths,
            f"{_mod}._build_report_html": mock_html,
            f"{_mod}._build_leaderboard_views": mock_lb_views,
            f"{_mod}._build_leaderboard_report_html": mock_lb_report_html,
        }

        import contextlib
        with contextlib.ExitStack() as stack:
            for target, mock_obj in patches.items():
                stack.enter_context(patch(target, mock_obj))

            result = _run_finalize_pipeline(
                combo_path=combo_path,
                per_symbol_path=per_symbol_path,
                out_dir=out_dir,
                run_id=run_id,
                timeframe_configs=timeframe_configs,
                timeframe_days_map=timeframe_days_map,
                safe_int_fn=lambda x, d=0: int(x) if x is not None else d,
                min_avg_daily_trades_target=0.0,
                apply_quality_filters_fn=lambda df: df,
                top_by_score_fn=lambda df, top_n=10, **kw: (df.head(top_n), None),
                history_rows=20,
                top_by_score_leaderboard_fn=lambda df, top_n=10, **kw: (df.head(top_n), None),
                base_symbol="BTC/USDT",
                trade_symbols=["ETH/USDT"],
                exchange="binance",
                cache_dir=str(tmp_path / "cache"),
                cache_format="csv",
                vol_lookbacks=[3],
                vol_zs=[0.1],
                mom_lookbacks=[3],
                trade_mom_lookbacks=[3],
                rsi_window=3,
                bb_window=3,
                bb_alpha=2.0,
                atr_window=3,
                ma_pairs=[(3, 5)],
                obv_lookbacks=[3],
                volume_lookbacks=[3],
                roc_lookbacks=[3],
                cmf_lookbacks=[3],
                mfi_window=3,
                vroc_lookbacks=[3],
                ad_lookbacks=[3],
                cci_lookbacks=[3],
                willr_lookbacks=[3],
                adx_lookbacks=[3],
                trix_lookbacks=[3],
                dpo_lookbacks=[3],
                efi_lookbacks=[3],
                vwma_lookbacks=[3],
                ultosc_periods=(3, 5, 7),
                keltner_lookbacks=[3],
                donchian_lookbacks=[3],
                ppo_fast=3,
                ppo_slow=5,
                ppo_signal=3,
                chop_lookbacks=[3],
                init_cash_usdt=1000,
                capital_mode="shared",
                timeframe_ranges={"1h": "2024-01-01 -> 2024-01-09"},
                wf_train_days=3,
                wf_test_days=1,
                wf_step_days=1,
                wf_valid_days=0,
                wf_mode="anchored",
                indicator_param_fields=indicator_param_fields,
                fees=0.001,
                slippage_bps=0.0,
                spread_bps=0.0,
                funding_rate_daily=0.0,
                order_size_pct=0.5,
                max_concurrent_positions=1,
                labels=labels,
                config_sha256="test_hash",
                timestamp_utc="2024-01-01T00:00:00Z",
                ranking_config={"mode": "oos_sharpe"},
                leaderboard_path=leaderboard_path,
                run_metadata_path=run_metadata_path,
                run_metadata_path_run=run_metadata_path_run,
                registry_path=registry_path,
                timeframe_fingerprints={"1h": "test_fp"},
                search_mode="combo",
                config_path=None,
                combine_data_fingerprints_fn=_combine_data_fingerprints,
                write_run_metadata_fn=_write_run_metadata,
                update_run_registry_fn=_update_run_registry,
                combo_seed=42,
            )

        # Verify finalize result
        assert result is not None
        assert isinstance(result, dict)
        assert result.get("ok") is True, f"Pipeline failed: {result}"

        # Verify key artifact files exist
        assert os.path.exists(leaderboard_path), "leaderboard.csv missing"
        assert os.path.exists(run_metadata_path), "run_metadata.json missing"
        assert os.path.exists(run_metadata_path_run), f"run_metadata_{run_id}.json missing"
        assert os.path.exists(registry_path), "run_registry.json missing"

        # Verify run_metadata content
        with open(run_metadata_path, "r") as f:
            meta = json.load(f)
        assert meta["run_id"] == run_id
        assert meta["config_sha256"] == "test_hash"
        assert meta["combo_seed"] == 42

        # Verify registry content
        with open(registry_path, "r") as f:
            reg = json.load(f)
        assert "runs" in reg
        assert len(reg["runs"]) >= 1

        # Verify run snapshot CSVs
        snap_combo = os.path.join(
            out_dir, f"param_sweep_combo_summary_{run_id}.csv"
        )
        snap_symbol = os.path.join(
            out_dir, f"param_sweep_symbol_summary_{run_id}.csv"
        )
        assert os.path.exists(snap_combo), "combo snapshot CSV missing"
        assert os.path.exists(snap_symbol), "symbol snapshot CSV missing"

    def test_finalize_empty_combo_returns_warning(self, tmp_path):
        """Finalize with empty combo CSV should return a warning result."""
        from autowfo.engine_finalize import _run_finalize_pipeline

        out_dir = str(tmp_path / "empty_artifacts")
        os.makedirs(out_dir, exist_ok=True)

        combo_path = os.path.join(out_dir, "combo.csv")
        symbol_path = os.path.join(out_dir, "symbol.csv")
        # Write CSV with headers only (no data rows) to trigger empty-current path
        pd.DataFrame(columns=["timeframe"]).to_csv(combo_path, index=False)
        pd.DataFrame(columns=["timeframe"]).to_csv(symbol_path, index=False)

        # Minimal kwargs ??most won't be reached because combo_df is empty
        result = _run_finalize_pipeline(
            combo_path=combo_path,
            per_symbol_path=symbol_path,
            out_dir=out_dir,
            run_id="empty_run",
            timeframe_configs=[{"timeframe": "1h", "days": 10}],
            timeframe_days_map={"1h": 10},
            safe_int_fn=lambda x, d=0: int(x) if x is not None else d,
            min_avg_daily_trades_target=0.0,
            apply_quality_filters_fn=lambda df: df,
            top_by_score_fn=lambda df, n=10, **kw: df.head(n),
            history_rows=20,
            top_by_score_leaderboard_fn=lambda df, n=10, **kw: df.head(n),
            base_symbol="BTC/USDT",
            trade_symbols=["ETH/USDT"],
            exchange="binance",
            cache_dir=str(tmp_path / "cache"),
            cache_format="csv",
            vol_lookbacks=[3],
            vol_zs=[0.1],
            mom_lookbacks=[3],
            trade_mom_lookbacks=[3],
            rsi_window=3,
            bb_window=3,
            bb_alpha=2.0,
            atr_window=3,
            ma_pairs=[(3, 5)],
            obv_lookbacks=[3],
            volume_lookbacks=[3],
            roc_lookbacks=[3],
            cmf_lookbacks=[3],
            mfi_window=3,
            vroc_lookbacks=[3],
            ad_lookbacks=[3],
            cci_lookbacks=[3],
            willr_lookbacks=[3],
            adx_lookbacks=[3],
            trix_lookbacks=[3],
            dpo_lookbacks=[3],
            efi_lookbacks=[3],
            vwma_lookbacks=[3],
            ultosc_periods=(3, 5, 7),
            keltner_lookbacks=[3],
            donchian_lookbacks=[3],
            ppo_fast=3,
            ppo_slow=5,
            ppo_signal=3,
            chop_lookbacks=[3],
            init_cash_usdt=1000,
            capital_mode="shared",
            timeframe_ranges={},
            wf_train_days=3,
            wf_test_days=1,
            wf_step_days=1,
            wf_valid_days=0,
            wf_mode="anchored",
            indicator_param_fields=[],
            fees=0.001,
            slippage_bps=0.0,
            spread_bps=0.0,
            funding_rate_daily=0.0,
            order_size_pct=0.5,
            max_concurrent_positions=1,
            labels={},
            config_sha256="test",
            timestamp_utc="2024-01-01T00:00:00Z",
            ranking_config=None,
            leaderboard_path=os.path.join(out_dir, "leaderboard.csv"),
            run_metadata_path=os.path.join(out_dir, "meta.json"),
            run_metadata_path_run=os.path.join(out_dir, "meta_run.json"),
            registry_path=os.path.join(out_dir, "reg.json"),
            timeframe_fingerprints={},
            search_mode="combo",
            config_path=None,
        )

        assert result is not None
        assert result.get("ok") is False
        assert "warning" in result

