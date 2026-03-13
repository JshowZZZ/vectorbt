from autowfo.experiment import Experiment
from autowfo.pool_discovery import generate_combinations, generate_experiment_configs


def test_generate_combinations_pool5_size2_returns_10_configs():
    pool_config = {
        "indicator_ids": ["RSI", "MACD", "BB", "EMA", "Volume"],
        "combo_size_range": [2, 2],
    }
    configs = generate_combinations(pool_config, analytics_store=None)
    assert len(configs) == 10
    ids = [cfg["experiment_id"] for cfg in configs]
    assert len(ids) == len(set(ids))
    assert all(exp_id.startswith("discovery_") for exp_id in ids)


def test_pruning_filters_known_low_effectiveness_combos():
    class StubAnalyticsStore:
        def query_indicator_leaderboard(self, limit=500):
            _ = limit
            return [
                {"trigger_indicators": '["RSI"]', "action_indicators": '["MACD"]', "avg_sharpe": 3.0},
                {"trigger_indicators": '["BB"]', "action_indicators": '["EMA"]', "avg_sharpe": 0.2},
                {"trigger_indicators": '["Volume"]', "action_indicators": '["BB"]', "avg_sharpe": 0.1},
            ]

    pool_config = {
        "indicator_ids": ["RSI", "MACD", "BB", "EMA", "Volume"],
        "combo_size_range": [2, 2],
        "pruning": {
            "enabled": True,
            "warmup_count": 0,
            "indicator_min_samples": 1,
            "prune_ratio": 2.0,
        },
    }
    configs = generate_experiment_configs(pool_config, analytics_store=StubAnalyticsStore())
    assert 0 < len(configs) < 10


def test_empty_pool_returns_empty_list():
    pool_config = {"indicator_ids": [], "combo_size_range": [2, 4]}
    configs = generate_experiment_configs(pool_config, analytics_store=None)
    assert configs == []


def test_generate_combinations_returns_valid_experiment_configs():
    pool_config = {
        "indicator_ids": ["RSI", "MACD", "BB", "EMA", "Volume"],
        "combo_sizes": [2],
        "default_trigger": {
            "asset": "BTC/USDT",
            "timeframe": "1h",
            "require_all": True,
        },
        "default_action": {
            "asset": "ETH/USDT",
            "timeframe": "4h",
            "require_all": True,
            "direction": "long",
        },
        "default_risk": {
            "stoploss_pct_values": [-2],
            "take_profit_pct_values": [3],
            "max_hold_bars_values": [24],
        },
        "default_wf": {"train_days": 30, "test_days": 10, "step_days": 10},
    }
    configs = generate_combinations(pool_config, analytics_store=None)
    assert len(configs) == 10
    for cfg in configs:
        exp = Experiment.from_dict(cfg)
        assert exp.experiment_id.startswith("discovery_")

