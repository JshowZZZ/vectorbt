"""Tests for AWF-022 ??combo intelligent pruning."""

import math

import pandas as pd
import pytest

from autowfo.pruning import PruningTracker, _default_pruning_config, _split_into_batches


# ---------------------------------------------------------------------------
# _default_pruning_config
# ---------------------------------------------------------------------------

def test_default_pruning_config_keys():
    cfg = _default_pruning_config()
    expected_keys = {
        "enabled", "warmup_count", "prune_ratio", "batch_size",
        "max_combos_evaluated", "top_n_track", "indicator_min_samples",
    }
    assert set(cfg.keys()) == expected_keys


def test_default_pruning_config_values():
    cfg = _default_pruning_config()
    assert cfg["enabled"] is True
    assert cfg["warmup_count"] == 500
    assert cfg["prune_ratio"] == 0.3
    assert cfg["batch_size"] == 2000
    assert cfg["max_combos_evaluated"] == 0
    assert cfg["top_n_track"] == 50
    assert cfg["indicator_min_samples"] == 20


# ---------------------------------------------------------------------------
# _split_into_batches
# ---------------------------------------------------------------------------

def test_split_into_batches_exact():
    items = list(range(6))
    batches = _split_into_batches(items, 3)
    assert batches == [[0, 1, 2], [3, 4, 5]]


def test_split_into_batches_remainder():
    items = list(range(7))
    batches = _split_into_batches(items, 3)
    assert batches == [[0, 1, 2], [3, 4, 5], [6]]


def test_split_into_batches_empty():
    assert _split_into_batches([], 10) == []


def test_split_into_batches_zero_size():
    items = [1, 2, 3]
    batches = _split_into_batches(items, 0)
    assert batches == [[1, 2, 3]]


def test_split_into_batches_large_batch():
    items = [1, 2]
    batches = _split_into_batches(items, 100)
    assert batches == [[1, 2]]


# ---------------------------------------------------------------------------
# PruningTracker ??construction
# ---------------------------------------------------------------------------

def test_tracker_default_construction():
    tracker = PruningTracker()
    assert tracker.enabled is True
    assert tracker.warmup_count == 500
    assert tracker.evaluated_count == 0
    assert tracker.pruned_count == 0
    assert tracker.score_threshold == -math.inf


def test_tracker_custom_config():
    tracker = PruningTracker({"enabled": False, "warmup_count": 10, "prune_ratio": 0.5})
    assert tracker.enabled is False
    assert tracker.warmup_count == 10
    assert tracker.prune_ratio == 0.5


def test_tracker_disabled_never_prunes():
    tracker = PruningTracker({"enabled": False, "warmup_count": 0})
    for i in range(100):
        tracker.record_result(("rsi",), float(i))
    tracker.update_threshold()
    assert tracker.should_prune(("rsi",)) is False


# ---------------------------------------------------------------------------
# PruningTracker ??should_prune logic
# ---------------------------------------------------------------------------

def test_tracker_no_prune_before_warmup():
    tracker = PruningTracker({"warmup_count": 10, "indicator_min_samples": 1, "prune_ratio": 0.5})
    # Record 5 results ??below warmup_count=10
    for i in range(5):
        tracker.record_result(("rsi",), 10.0)
    tracker.update_threshold()
    assert tracker.should_prune(("rsi",)) is False


def test_tracker_prune_after_warmup():
    tracker = PruningTracker({
        "warmup_count": 5,
        "indicator_min_samples": 3,
        "prune_ratio": 0.5,
        "top_n_track": 10,
    })
    # Record 10 high-scoring combos for "rsi"
    for i in range(10):
        tracker.record_result(("rsi",), 100.0)
    tracker.update_threshold()
    # Record 10 low-scoring combos for "bb"
    for i in range(10):
        tracker.record_result(("bb",), -50.0)
    tracker.update_threshold()

    # "bb" alone should be pruned (predicted score = -50, threshold = 100*0.5 = 50)
    assert tracker.should_prune(("bb",)) is True
    # "rsi" alone should NOT be pruned (predicted score = 100 > 50)
    assert tracker.should_prune(("rsi",)) is False


def test_tracker_no_prune_insufficient_indicator_samples():
    tracker = PruningTracker({
        "warmup_count": 5,
        "indicator_min_samples": 20,
        "prune_ratio": 0.5,
        "top_n_track": 10,
    })
    for i in range(10):
        tracker.record_result(("rsi",), 100.0)
    tracker.update_threshold()
    # "rsi" has only 10 samples but min_samples=20 ??can't prune
    assert tracker.should_prune(("rsi",)) is False


def test_tracker_prune_zero_ratio_disabled():
    tracker = PruningTracker({
        "warmup_count": 1,
        "indicator_min_samples": 1,
        "prune_ratio": 0.0,
        "top_n_track": 5,
    })
    for i in range(10):
        tracker.record_result(("rsi",), 100.0)
    for i in range(10):
        tracker.record_result(("bb",), -100.0)
    tracker.update_threshold()
    # prune_ratio=0 disables score pruning
    assert tracker.should_prune(("bb",)) is False


def test_tracker_multi_indicator_combo_prediction():
    """Predicted score for a multi-indicator combo is the mean of per-indicator averages."""
    tracker = PruningTracker({
        "warmup_count": 3,
        "indicator_min_samples": 3,
        "prune_ratio": 0.3,
        "top_n_track": 10,
    })
    # "rsi" scores: avg = 50
    for _ in range(5):
        tracker.record_result(("rsi",), 50.0)
    # "bb" scores: avg = 10
    for _ in range(5):
        tracker.record_result(("bb",), 10.0)
    tracker.update_threshold()
    # Predicted for ("rsi", "bb") = (50 + 10) / 2 = 30
    # Since all scores are 50 or 10, top-N median is 50
    # threshold = 50 * 0.3 = 15
    # 30 >= 15 ??should NOT be pruned
    assert tracker.should_prune(("rsi", "bb")) is False


# ---------------------------------------------------------------------------
# PruningTracker ??budget_exhausted
# ---------------------------------------------------------------------------

def test_tracker_budget_unlimited():
    tracker = PruningTracker({"max_combos_evaluated": 0})
    for i in range(1000):
        tracker.record_result(("rsi",), 1.0)
    assert tracker.budget_exhausted() is False


def test_tracker_budget_limited():
    tracker = PruningTracker({"max_combos_evaluated": 5})
    for i in range(5):
        tracker.record_result(("rsi",), 1.0)
    assert tracker.budget_exhausted() is True


def test_tracker_budget_not_yet_exhausted():
    tracker = PruningTracker({"max_combos_evaluated": 10})
    for i in range(3):
        tracker.record_result(("rsi",), 1.0)
    assert tracker.budget_exhausted() is False


# ---------------------------------------------------------------------------
# PruningTracker ??record_result / increment_pruned
# ---------------------------------------------------------------------------

def test_tracker_record_nan_score():
    tracker = PruningTracker()
    tracker.record_result(("rsi",), float("nan"))
    assert tracker.evaluated_count == 1
    assert tracker._indicator_scores["rsi"] == [0.0]


def test_tracker_record_none_score():
    tracker = PruningTracker()
    tracker.record_result(("rsi",), None)
    assert tracker.evaluated_count == 1
    assert tracker._indicator_scores["rsi"] == [0.0]


def test_tracker_increment_pruned():
    tracker = PruningTracker()
    assert tracker.pruned_count == 0
    tracker.increment_pruned()
    tracker.increment_pruned()
    assert tracker.pruned_count == 2


# ---------------------------------------------------------------------------
# PruningTracker ??warm_start
# ---------------------------------------------------------------------------

def test_warm_start_from_dataframe():
    tracker = PruningTracker({"top_n_track": 5, "indicator_min_samples": 1})
    df = pd.DataFrame({
        "indicator_list": ["rsi,bb", "rsi,macd", "bb,macd"],
        "oos_avg_total_return_pct": [10.0, 20.0, -5.0],
    })
    tracker.warm_start(df)
    assert tracker.evaluated_count == 3
    assert len(tracker._indicator_scores["rsi"]) == 2
    assert len(tracker._indicator_scores["bb"]) == 2
    assert len(tracker._indicator_scores["macd"]) == 2
    assert tracker.score_threshold != -math.inf


def test_warm_start_empty_df():
    tracker = PruningTracker()
    tracker.warm_start(pd.DataFrame())
    assert tracker.evaluated_count == 0


def test_warm_start_none():
    tracker = PruningTracker()
    tracker.warm_start(None)
    assert tracker.evaluated_count == 0


def test_warm_start_missing_columns():
    tracker = PruningTracker()
    df = pd.DataFrame({"other_col": [1, 2, 3]})
    tracker.warm_start(df)
    assert tracker.evaluated_count == 0


def test_warm_start_with_nan_scores():
    tracker = PruningTracker({"top_n_track": 5})
    df = pd.DataFrame({
        "indicator_list": ["rsi,bb", "rsi,macd"],
        "oos_avg_total_return_pct": [10.0, float("nan")],
    })
    tracker.warm_start(df)
    assert tracker.evaluated_count == 1  # NaN row skipped


# ---------------------------------------------------------------------------
# PruningTracker ??summary
# ---------------------------------------------------------------------------

def test_tracker_summary():
    tracker = PruningTracker()
    tracker.record_result(("rsi",), 10.0)
    tracker.increment_pruned()
    s = tracker.summary()
    assert s["evaluated"] == 1
    assert s["pruned"] == 1
    assert s["enabled"] is True
    assert "score_threshold" in s
    assert "top_scores_len" in s
    assert "indicator_count" in s


# ---------------------------------------------------------------------------
# PruningTracker ??top-N and threshold
# ---------------------------------------------------------------------------

def test_top_n_cap():
    tracker = PruningTracker({"top_n_track": 3})
    for i in range(10):
        tracker.record_result(("rsi",), float(i))
    assert len(tracker._top_scores) == 3
    assert tracker._top_scores == [7.0, 8.0, 9.0]


def test_threshold_computation():
    tracker = PruningTracker({"top_n_track": 5, "prune_ratio": 0.5})
    scores = [10.0, 20.0, 30.0, 40.0, 50.0]
    for s in scores:
        tracker.record_result(("rsi",), s)
    tracker.update_threshold()
    # Sorted top-5: [10, 20, 30, 40, 50], median (index 2) = 30
    # threshold = 30 * 0.5 = 15.0
    assert tracker.score_threshold == 15.0


# ---------------------------------------------------------------------------
# Integration: _run_combo_eval_step with pruning
# ---------------------------------------------------------------------------

def test_run_combo_eval_step_prunes_low_scoring_combo():
    from autowfo.engine_search import _run_combo_eval_step

    tracker = PruningTracker({
        "warmup_count": 3,
        "indicator_min_samples": 3,
        "prune_ratio": 0.5,
        "top_n_track": 5,
    })
    # Warm up with high scores for "rsi"
    for _ in range(5):
        tracker.record_result(("rsi",), 100.0)
    # Record low scores for "bad_ind"
    for _ in range(5):
        tracker.record_result(("bad_ind",), -100.0)
    tracker.update_threshold()

    progress_ticks = []

    def tick(done_delta, skipped_delta):
        progress_ticks.append((done_delta, skipped_delta))

    result = _run_combo_eval_step(
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        indicator_combo=("bad_ind",),
        combo_params={},
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        stage="test combo",
        wait_if_paused_fn=lambda stage: None,
        build_combo_task_fn=lambda **kw: ("key1", {"combo_key": "key1", "indicator_combo": kw["indicator_combo"]}),
        seen_keys=set(),
        evaluate_combo_task_fn=lambda t, r: {"metrics_values": {}, "oos_metrics": {"oos_avg_total_return_pct": -90}},
        runtime_eval={},
        append_eval_result_fn=lambda result, task_meta: None,
        emit_progress_fn=lambda stage: None,
        checkpoint_fn=lambda: None,
        on_progress_tick_fn=tick,
        pruning_tracker=tracker,
    )

    assert result["skipped"] is True
    assert result.get("pruned") is True
    assert len(progress_ticks) == 1
    assert progress_ticks[0] == (1, 1)


def test_run_combo_eval_step_no_prune_good_combo():
    from autowfo.engine_search import _run_combo_eval_step

    tracker = PruningTracker({
        "warmup_count": 3,
        "indicator_min_samples": 3,
        "prune_ratio": 0.5,
        "top_n_track": 5,
    })
    for _ in range(5):
        tracker.record_result(("rsi",), 100.0)
    tracker.update_threshold()

    evaluated = []

    def fake_eval(task, runtime):
        evaluated.append(task)
        return {
            "metrics_values": {},
            "oos_metrics": {"oos_avg_total_return_pct": 80.0},
            "variant_params": {},
            "combo_metrics": {},
            "sym_metrics": {},
        }

    result = _run_combo_eval_step(
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        indicator_combo=("rsi",),
        combo_params={},
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        stage="test combo",
        wait_if_paused_fn=lambda stage: None,
        build_combo_task_fn=lambda **kw: ("key2", {"combo_key": "key2", "indicator_combo": kw["indicator_combo"]}),
        seen_keys=set(),
        evaluate_combo_task_fn=fake_eval,
        runtime_eval={},
        append_eval_result_fn=lambda result, task_meta: None,
        emit_progress_fn=lambda stage: None,
        checkpoint_fn=lambda: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        pruning_tracker=tracker,
    )

    assert result["evaluated"] is True
    assert result["skipped"] is False
    assert len(evaluated) == 1


def test_run_combo_eval_step_budget_exhausted():
    from autowfo.engine_search import _run_combo_eval_step

    tracker = PruningTracker({"max_combos_evaluated": 5})
    for _ in range(5):
        tracker.record_result(("rsi",), 10.0)

    result = _run_combo_eval_step(
        regime={"regime_name": "trend_high", "regime_type": "trend", "vol_mode": "high"},
        indicator_combo=("rsi",),
        combo_params={},
        vol_lookback=24,
        vol_z=0.8,
        mom_lookback=6,
        trade_mom_lookback=3,
        tp_stop=0.003,
        sl_stop=0.006,
        max_hold=2,
        stage="test combo",
        wait_if_paused_fn=lambda stage: None,
        build_combo_task_fn=lambda **kw: ("key3", {"combo_key": "key3", "indicator_combo": kw["indicator_combo"]}),
        seen_keys=set(),
        evaluate_combo_task_fn=lambda t, r: None,
        runtime_eval={},
        append_eval_result_fn=lambda result, task_meta: None,
        emit_progress_fn=lambda stage: None,
        checkpoint_fn=lambda: None,
        on_progress_tick_fn=lambda done_delta, skipped_delta: None,
        pruning_tracker=tracker,
    )

    assert result["skipped"] is True
    assert result.get("budget") is True


# ---------------------------------------------------------------------------
# Integration: engine_helpers pruning_config extraction
# ---------------------------------------------------------------------------

def test_resolve_runtime_settings_includes_pruning_config():
    from autowfo.engine_helpers import _resolve_runtime_settings
    from autowfo.split import _normalize_split_mode
    from autowfo.ranking import _resolve_ranking_config

    default_config = {
        "search_mode": "combo",
        "timeframes": [{"timeframe": "1h", "days": 365}],
        "combo_sizes": [2, 3],
        "pruning": {
            "enabled": True,
            "warmup_count": 100,
            "prune_ratio": 0.4,
        },
    }
    settings = _resolve_runtime_settings(
        default_config,
        base_symbol="BTC/USDT",
        default_trade_symbols=["ETH/BTC"],
        normalize_split_mode_fn=_normalize_split_mode,
        resolve_ranking_config_fn=_resolve_ranking_config,
    )
    assert settings["pruning_config"] is not None
    assert settings["pruning_config"]["enabled"] is True
    assert settings["pruning_config"]["warmup_count"] == 100
    assert settings["pruning_config"]["prune_ratio"] == 0.4


def test_resolve_runtime_settings_no_pruning_config():
    from autowfo.engine_helpers import _resolve_runtime_settings
    from autowfo.split import _normalize_split_mode
    from autowfo.ranking import _resolve_ranking_config

    default_config = {
        "search_mode": "combo",
        "timeframes": [{"timeframe": "1h", "days": 365}],
        "combo_sizes": [2, 3],
    }
    settings = _resolve_runtime_settings(
        default_config,
        base_symbol="BTC/USDT",
        default_trade_symbols=["ETH/BTC"],
        normalize_split_mode_fn=_normalize_split_mode,
        resolve_ranking_config_fn=_resolve_ranking_config,
    )
    assert settings["pruning_config"] is None


# ---------------------------------------------------------------------------
# Integration: context builders forward pruning_config
# ---------------------------------------------------------------------------

def test_build_timeframe_ready_search_context_includes_pruning_config():
    from autowfo.engine_search import _build_timeframe_ready_search_context

    pruning_cfg = {"enabled": True, "warmup_count": 200}
    # Build a minimal context ??we only verify pruning_config is forwarded
    ctx = _build_timeframe_ready_search_context(
        search_mode="combo",
        max_workers=1,
        regime_variants=[],
        regime_lookup={},
        mom_lookbacks=[6],
        vol_lookbacks=[24],
        vol_zs=[0.8],
        trade_mom_lookbacks=[3],
        tp_stops=[0.003],
        sl_stops=[0.006],
        max_holds=[2],
        combo_keys_all=[],
        indicator_param_options={},
        existing_combo_df=pd.DataFrame(),
        combo_group_fields=[],
        top_n_fine=10,
        min_avg_daily_trades_target=5.0,
        indicator_defaults={},
        indicator_param_fields=[],
        exchange="binance",
        base_symbol="BTC/USDT",
        capital_mode="shared",
        fees=0.001,
        slippage_bps=0.0,
        spread_bps=0.0,
        funding_rate_daily=0.0,
        order_size_pct=0.5,
        max_concurrent_positions=2,
        init_cash_usdt=1000,
        wf_train_days=120,
        wf_test_days=30,
        wf_step_days=30,
        wf_mode="anchored",
        rsi_window=14,
        config_sha256="abc123",
        ranking_config=None,
        seen_keys=set(),
        pending_symbol_rows=[],
        pending_combo_rows=[],
        combo_key_from_dict_fn=lambda d: "",
        indicator_combo_label_fn=lambda c: "",
        iter_indicator_param_combos_fn=lambda c, o: iter([]),
        run_combo_tasks_fn=lambda t, r, max_workers=1: [],
        evaluate_combo_task_fn=lambda t, r: {},
        wait_if_paused_fn=lambda s: None,
        emit_progress_fn=lambda stage: None,
        checkpoint_fn=lambda: None,
        on_progress_tick_fn=None,
        apply_quality_filters_fn=lambda df: (df, None),
        sort_by_score_impl_fn=lambda df, tie_break_avg_hold=True, ranking_config=None: (df, None),
        expand_float_fn=lambda v, step, min_value=0: [v],
        safe_float_fn=lambda v, d: d,
        refine_indicator_params_fn=lambda k, r, s, d: [{}],
        safe_int_fn=lambda v, d: d,
        pruning_config=pruning_cfg,
    )

    assert ctx["pruning_config"] == pruning_cfg

