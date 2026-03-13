import json

import pytest

from autowfo.experiment import Experiment


def _valid_config():
    return {
        "experiment_id": "exp_btc1h_eth4h_rsi_bb_v1",
        "description": "BTC RSI trigger with ETH BB action",
        "version": 1,
        "created_utc": "2026-03-01T00:00:00Z",
        "mode": "hypothesis",
        "trigger": {
            "asset": "BTC/USDT",
            "timeframe": "1h",
            "indicators": ["RSI"],
            "conditions": {
                "RSI": {
                    "operator": "below",
                    "param_name": "rsi_period",
                    "param_values": [14, 21],
                    "threshold_values": [25, 30],
                }
            },
            "require_all": True,
        },
        "action": {
            "asset": "ETH/USDT",
            "timeframe": "4h",
            "indicators": ["BB"],
            "conditions": {
                "BB": {
                    "operator": "near_lower",
                    "bb_period_values": [20],
                    "pct_values": [0.02, 0.05],
                }
            },
            "require_all": True,
            "direction": "both",
        },
        "risk": {
            "stoploss_pct_values": [-3],
            "take_profit_pct_values": [5],
            "max_hold_bars_values": [24],
        },
        "wf": {
            "train_days": 90,
            "test_days": 30,
            "step_days": 30,
        },
    }


def test_from_dict_valid_config():
    exp = Experiment.from_dict(_valid_config())
    assert exp.experiment_id == "exp_btc1h_eth4h_rsi_bb_v1"


def test_expand_grid_returns_expected_count_and_direction_both():
    exp = Experiment.from_dict(_valid_config())
    grid = exp.expand_grid()
    assert len(grid) == 16  # 2*2*1*2*1*1*2 directions
    directions = {row["direction"] for row in grid}
    assert directions == {"long", "short"}


def test_expand_grid_is_deterministic():
    exp = Experiment.from_dict(_valid_config())
    grid_a = exp.expand_grid()
    grid_b = exp.expand_grid()
    assert grid_a == grid_b


def test_expand_grid_empty_values_uses_default():
    config = _valid_config()
    config["trigger"]["conditions"]["RSI"]["param_values"] = []
    exp = Experiment.from_dict(config)
    grid = exp.expand_grid()
    assert any(row.get("trigger_rsi_period") == 14 for row in grid)


def test_validation_rule_1_experiment_id():
    config = _valid_config()
    config["experiment_id"] = "exp-invalid-id"
    with pytest.raises(ValueError, match="experiment_id"):
        Experiment.from_dict(config)


def test_validation_rule_2_assets_non_empty():
    config = _valid_config()
    config["trigger"]["asset"] = ""
    with pytest.raises(ValueError, match="asset"):
        Experiment.from_dict(config)


def test_validation_rule_3_timeframes_non_empty():
    config = _valid_config()
    config["action"]["timeframe"] = ""
    with pytest.raises(ValueError, match="timeframe"):
        Experiment.from_dict(config)


def test_validation_rule_4_trigger_indicator_in_registry():
    config = _valid_config()
    config["trigger"]["indicators"] = ["NOT_EXISTS"]
    with pytest.raises(ValueError, match="unknown indicator"):
        Experiment.from_dict(config)


def test_validation_rule_5_operator_in_registry():
    config = _valid_config()
    config["trigger"]["conditions"]["RSI"]["operator"] = "nope"
    with pytest.raises(ValueError, match="operator"):
        Experiment.from_dict(config)


def test_validation_rule_6_wf_constraints():
    config = _valid_config()
    config["wf"]["step_days"] = 10
    config["wf"]["test_days"] = 30
    with pytest.raises(ValueError, match="wf"):
        Experiment.from_dict(config)


def test_validation_rule_7_stoploss_negative():
    config = _valid_config()
    config["risk"]["stoploss_pct_values"] = [-3, 5]
    with pytest.raises(ValueError, match="stoploss"):
        Experiment.from_dict(config)


def test_validation_rule_8_take_profit_positive():
    config = _valid_config()
    config["risk"]["take_profit_pct_values"] = [5, -2]
    with pytest.raises(ValueError, match="take_profit"):
        Experiment.from_dict(config)


def test_validation_rule_9_mode_allowed_values():
    config = _valid_config()
    config["mode"] = "other"
    with pytest.raises(ValueError, match="mode"):
        Experiment.from_dict(config)


def test_save_and_from_json_roundtrip(tmp_path):
    exp = Experiment.from_dict(_valid_config())
    out_path = tmp_path / "exp" / "config.json"
    exp.save(out_path)
    assert out_path.exists()

    loaded = Experiment.from_json(out_path)
    assert loaded.config == exp.config
    # sanity check serialized JSON is valid
    parsed = json.loads(out_path.read_text(encoding="utf-8"))
    assert parsed["experiment_id"] == exp.experiment_id


def test_artifact_dir_relative_path():
    exp = Experiment.from_dict(_valid_config())
    assert exp.artifact_dir.as_posix() == "artifacts/experiments/exp_btc1h_eth4h_rsi_bb_v1"


