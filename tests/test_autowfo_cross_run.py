import json
from pathlib import Path

import pytest

from autowfo import cross_run


def _write_csv(path: Path, header, rows):
    import csv as _csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in header})


def test_build_cross_run_payload_with_combo_stability(tmp_path):
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "r2",
                        "timestamp_utc": "2026-02-10T02:00:00Z",
                        "search_mode": "refine",
                        "timeframes": [{"timeframe": "1h", "days": 90}],
                        "trade_symbols": ["ETH/USDT"],
                        "best_timeframe": "1h",
                        "oos_avg_total_return_pct": 2.5,
                        "avg_total_return_pct": 1.8,
                    },
                    {
                        "run_id": "r1",
                        "timestamp_utc": "2026-02-10T01:00:00Z",
                        "search_mode": "combo",
                        "timeframes": [{"timeframe": "4h", "days": 180}],
                        "trade_symbols": ["ETH/USDT", "SOL/USDT"],
                        "best_timeframe": "4h",
                        "oos_avg_total_return_pct": 1.2,
                        "avg_total_return_pct": 0.9,
                    },
                ],
                "coverage": {
                    "tested_pairs": [
                        {"timeframe": "1h", "symbol": "ETH/USDT"},
                        {"timeframe": "4h", "symbol": "ETH/USDT"},
                    ],
                    "untested_pairs": [
                        {"timeframe": "1h", "symbol": "SOL/USDT"},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct", "oos_avg_max_drawdown_pct"]
    _write_csv(
        artifacts / "runs" / "runA" / "refine" / "param_sweep_top10_r1.csv",
        header,
        [
            {
                "indicator_list": "rsi,roc",
                "regime_name": "trend_high",
                "vol_mode": "normal",
                "oos_avg_total_return_pct": 1.2,
                "oos_avg_max_drawdown_pct": -4.0,
            },
            {
                "indicator_list": "mfi,cmf",
                "regime_name": "trend_high",
                "vol_mode": "normal",
                "oos_avg_total_return_pct": 0.8,
                "oos_avg_max_drawdown_pct": -3.0,
            },
        ],
    )
    _write_csv(
        artifacts / "runs" / "runB" / "refine" / "param_sweep_top10_r2.csv",
        header,
        [
            {
                "indicator_list": "rsi,roc",
                "regime_name": "trend_high",
                "vol_mode": "normal",
                "oos_avg_total_return_pct": 2.5,
                "oos_avg_max_drawdown_pct": -5.5,
            }
        ],
    )

    payload = cross_run.build_cross_run_payload(
        artifacts_dir=artifacts,
        registry_path=registry_path,
        top_n=10,
    )
    assert payload["summary"]["total_runs"] == 2
    assert payload["summary"]["unique_symbols"] == 2
    assert payload["summary"]["coverage_pct"] == 66.67
    assert payload["global_leaderboard"][0]["run_id"] == "r2"
    assert payload["combo_stability"][0]["appearances"] == 2
    assert "r1" in payload["combo_stability"][0]["run_ids"]
    assert "r2" in payload["combo_stability"][0]["run_ids"]


def test_benchmark_fields_propagated_to_leaderboard(tmp_path):
    """Runs with bh_return_pct / random_entry_return_pct ??leaderboard + summary."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "b1",
                        "timestamp_utc": "2026-02-14T01:00:00Z",
                        "search_mode": "combo",
                        "timeframes": [{"timeframe": "2h", "days": 120}],
                        "trade_symbols": ["ETH/USDT"],
                        "best_timeframe": "2h",
                        "oos_avg_total_return_pct": 5.0,
                        "avg_total_return_pct": 3.0,
                        "bh_return_pct": 2.0,
                        "random_entry_return_pct": 0.5,
                    },
                    {
                        "run_id": "b2",
                        "timestamp_utc": "2026-02-14T02:00:00Z",
                        "search_mode": "combo",
                        "timeframes": [{"timeframe": "4h", "days": 180}],
                        "trade_symbols": ["BNB/USDT"],
                        "best_timeframe": "4h",
                        "oos_avg_total_return_pct": 3.0,
                        "avg_total_return_pct": 2.0,
                        "bh_return_pct": 1.0,
                        "random_entry_return_pct": -0.2,
                    },
                ],
                "coverage": {"tested_pairs": [], "untested_pairs": []},
            }
        ),
        encoding="utf-8",
    )
    payload = cross_run.build_cross_run_payload(
        artifacts_dir=artifacts, registry_path=registry_path, top_n=10,
    )
    # Leaderboard row 0 should be b1 (higher OOS)
    lb0 = payload["global_leaderboard"][0]
    assert lb0["bh_return_pct"] == 2.0
    assert lb0["random_entry_return_pct"] == 0.5
    assert lb0["alpha_vs_bh"] == pytest.approx(3.0)  # 5.0 - 2.0

    # Summary aggregates
    s = payload["summary"]
    assert s["avg_bh_return_pct"] == pytest.approx(1.5)       # (2+1)/2
    assert s["avg_random_return_pct"] == pytest.approx(0.15)   # (0.5+(-0.2))/2
    assert s["avg_alpha_vs_bh"] == pytest.approx(2.5)          # (3.0+2.0)/2


def test_benchmark_fields_none_when_absent(tmp_path):
    """Old registry entries without benchmark fields ??graceful None."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "old1",
                        "timestamp_utc": "2026-01-01T00:00:00Z",
                        "search_mode": "combo",
                        "timeframes": [{"timeframe": "4h", "days": 180}],
                        "trade_symbols": ["ETH/USDT"],
                        "best_timeframe": "4h",
                        "oos_avg_total_return_pct": 4.0,
                        "avg_total_return_pct": 2.5,
                        # no bh_return_pct, no random_entry_return_pct
                    },
                ],
                "coverage": {"tested_pairs": [], "untested_pairs": []},
            }
        ),
        encoding="utf-8",
    )
    payload = cross_run.build_cross_run_payload(
        artifacts_dir=artifacts, registry_path=registry_path, top_n=10,
    )
    lb = payload["global_leaderboard"][0]
    assert lb["bh_return_pct"] is None
    assert lb["random_entry_return_pct"] is None
    assert lb["alpha_vs_bh"] is None
    assert payload["summary"]["avg_bh_return_pct"] is None
    assert payload["summary"]["avg_random_return_pct"] is None
    assert payload["summary"]["avg_alpha_vs_bh"] is None


def test_benchmark_html_contains_new_columns(tmp_path):
    """Rendered HTML should contain the benchmark column headers."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "h1",
                        "timestamp_utc": "2026-02-14T00:00:00Z",
                        "search_mode": "combo",
                        "timeframes": [],
                        "trade_symbols": [],
                        "oos_avg_total_return_pct": 1.0,
                        "bh_return_pct": 0.5,
                        "random_entry_return_pct": 0.1,
                    }
                ],
                "coverage": {"tested_pairs": [], "untested_pairs": []},
            }
        ),
        encoding="utf-8",
    )
    payload = cross_run.build_cross_run_payload(
        artifacts_dir=artifacts, registry_path=registry_path, top_n=10,
    )
    html = cross_run.render_cross_run_html(payload)
    assert "bh_return_pct" in html
    assert "random_entry_return_pct" in html
    assert "alpha_vs_bh" in html
    assert "Avg BH Return %" in html
    assert "Avg Alpha vs BH" in html


def test_write_cross_run_reports_outputs_html_and_json(tmp_path):
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"runs": [], "coverage": {}}), encoding="utf-8")

    out_html = artifacts / "cross_run_report.html"
    out_json = artifacts / "cross_run_report.json"
    payload = cross_run.write_cross_run_reports(
        artifacts_dir=artifacts,
        registry_path=registry_path,
        out_html_path=out_html,
        out_json_path=out_json,
        top_n=20,
    )
    assert out_html.exists()
    assert out_json.exists()
    assert payload["summary"]["total_runs"] == 0
    assert "AUTOWFO Cross-Run Report" in out_html.read_text(encoding="utf-8")


def test_normalize_cross_run_payload_adds_schema_and_defaults():
    legacy_payload = {
        "generated_utc": "2026-02-20T00:00:00Z",
        "summary": {"total_runs": 3},
        "global_leaderboard": [{"run_id": "r1"}],
    }
    normalized = cross_run.normalize_cross_run_payload(legacy_payload, top_n=10)
    assert normalized["schema_version"] == cross_run.CROSS_RUN_PAYLOAD_SCHEMA_VERSION
    assert normalized["summary"]["total_runs"] == 3
    assert "coverage_pct" in normalized["summary"]
    assert isinstance(normalized["run_history"], list)
    assert isinstance(normalized["combo_stability"], list)
    assert isinstance(normalized["per_regime_leaderboard"], dict)
    assert isinstance(normalized["regime_summary"], list)


def test_normalize_cross_run_payload_migrates_schema_version_to_v1():
    legacy_payload = {
        "schema_version": "autowfo.cross_run_payload/v0",
        "summary": {"total_runs": 1},
    }
    normalized = cross_run.normalize_cross_run_payload(legacy_payload, top_n=10)
    assert normalized["schema_version"] == cross_run.CROSS_RUN_PAYLOAD_SCHEMA_VERSION
    assert normalized["source_schema_version"] == "autowfo.cross_run_payload/v0"


def test_normalize_cross_run_payload_applies_top_n_limit():
    legacy_payload = {
        "global_leaderboard": [
            {"run_id": "r1"},
            {"run_id": "r2"},
            {"run_id": "r3"},
        ]
    }
    normalized = cross_run.normalize_cross_run_payload(legacy_payload, top_n=2)
    assert [row["run_id"] for row in normalized["global_leaderboard"]] == ["r1", "r2"]


def test_load_cross_run_payload_invalid_json_raises(tmp_path):
    payload_path = tmp_path / "cross_run_report.json"
    payload_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(cross_run.CrossRunPayloadValidationError) as exc_info:
        cross_run.load_cross_run_payload(payload_path)
    assert exc_info.value.code == "invalid_json"


def test_load_cross_run_payload_missing_file_raises_typed_code(tmp_path):
    payload_path = tmp_path / "cross_run_report.json"
    with pytest.raises(cross_run.CrossRunPayloadValidationError) as exc_info:
        cross_run.load_cross_run_payload(payload_path)
    assert exc_info.value.code == "payload_file_missing"


def test_validate_cross_run_payload_accepts_normalized_v1():
    payload = cross_run.normalize_cross_run_payload({"summary": {"total_runs": 1}}, top_n=10)
    validated = cross_run.validate_cross_run_payload(payload, require_v1=True)
    assert validated["schema_version"] == cross_run.CROSS_RUN_PAYLOAD_SCHEMA_VERSION


def test_validate_cross_run_payload_raises_on_missing_summary_keys():
    bad_payload = {
        "schema_version": cross_run.CROSS_RUN_PAYLOAD_SCHEMA_VERSION,
        "generated_utc": "2026-02-20T00:00:00Z",
        "registry_path": "artifacts/run_registry.json",
        "summary": {"total_runs": 1},
        "run_history": [],
        "global_leaderboard": [],
        "combo_stability": [],
        "per_regime_leaderboard": {},
        "regime_summary": [],
    }
    with pytest.raises(cross_run.CrossRunPayloadValidationError, match="missing summary keys") as exc_info:
        cross_run.validate_cross_run_payload(bad_payload, require_v1=True)
    assert exc_info.value.code == "missing_summary_keys"


# ---------------------------------------------------------------------------
#  AWF-025: Combo stability trend analysis tests
# ---------------------------------------------------------------------------


def test_linear_slope_basic():
    assert cross_run._linear_slope([]) == 0.0
    assert cross_run._linear_slope([5.0]) == 0.0
    # Perfectly increasing: 1, 2, 3 ??slope = 1.0
    assert abs(cross_run._linear_slope([1.0, 2.0, 3.0]) - 1.0) < 1e-9
    # Perfectly decreasing: 3, 2, 1 ??slope = -1.0
    assert abs(cross_run._linear_slope([3.0, 2.0, 1.0]) - (-1.0)) < 1e-9
    # Flat: 5, 5, 5 ??slope = 0.0
    assert cross_run._linear_slope([5.0, 5.0, 5.0]) == 0.0


def test_trend_label_classification():
    assert cross_run._trend_label(0.10) == "improving"
    assert cross_run._trend_label(-0.10) == "declining"
    assert cross_run._trend_label(0.01) == "flat"
    assert cross_run._trend_label(0.0) == "flat"
    # Custom threshold
    assert cross_run._trend_label(0.03, threshold=0.02) == "improving"
    assert cross_run._trend_label(-0.03, threshold=0.02) == "declining"


def test_svg_sparkline_empty():
    assert cross_run._svg_sparkline([]) == ""


def test_svg_sparkline_has_svg_tag():
    svg = cross_run._svg_sparkline([1.0, 2.0, 3.0])
    assert svg.startswith("<svg ")
    assert "</svg>" in svg
    assert "polyline" in svg


def test_svg_sparkline_color_green_when_rising():
    svg = cross_run._svg_sparkline([1.0, 2.0, 3.0])
    assert "#27ae60" in svg  # green


def test_svg_sparkline_color_red_when_falling():
    svg = cross_run._svg_sparkline([3.0, 2.0, 1.0])
    assert "#e74c3c" in svg  # red


def test_compute_trend_metrics_empty():
    m = cross_run._compute_trend_metrics([])
    assert m["trend_direction"] == "flat"
    assert m["slope"] == 0.0
    assert m["return_std"] is None
    assert m["consistency_pct"] is None
    assert m["sparkline"] == ""


def test_compute_trend_metrics_single():
    m = cross_run._compute_trend_metrics([5.0])
    assert m["trend_direction"] == "flat"
    assert m["consistency_pct"] == 100.0
    assert m["return_std"] is None


def test_compute_trend_metrics_improving():
    m = cross_run._compute_trend_metrics([1.0, 2.0, 3.0, 4.0])
    assert m["trend_direction"] == "improving"
    assert m["slope"] > 0
    assert m["consistency_pct"] == 100.0
    assert m["return_std"] is not None
    assert m["sparkline"] != ""


def test_compute_trend_metrics_declining():
    m = cross_run._compute_trend_metrics([4.0, 3.0, 2.0, 1.0])
    assert m["trend_direction"] == "declining"
    assert m["slope"] < 0


def test_compute_trend_metrics_consistency():
    # 3 positive, 1 negative ??75%
    m = cross_run._compute_trend_metrics([1.0, -1.0, 2.0, 3.0])
    assert m["consistency_pct"] == 75.0


def test_build_combo_stability_includes_trend_fields(tmp_path):
    """_build_combo_stability should produce trend-enriched entries."""
    artifacts = tmp_path / "artifacts"

    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct", "oos_avg_max_drawdown_pct"]
    _write_csv(
        artifacts / "param_sweep_top10_r1.csv",
        header,
        [{"indicator_list": "rsi,roc", "regime_name": "trend_high", "vol_mode": "normal",
          "oos_avg_total_return_pct": 1.0, "oos_avg_max_drawdown_pct": -3.0}],
    )
    _write_csv(
        artifacts / "param_sweep_top10_r2.csv",
        header,
        [{"indicator_list": "rsi,roc", "regime_name": "trend_high", "vol_mode": "normal",
          "oos_avg_total_return_pct": 2.0, "oos_avg_max_drawdown_pct": -4.0}],
    )
    _write_csv(
        artifacts / "param_sweep_top10_r3.csv",
        header,
        [{"indicator_list": "rsi,roc", "regime_name": "trend_high", "vol_mode": "normal",
          "oos_avg_total_return_pct": 3.0, "oos_avg_max_drawdown_pct": -2.0}],
    )

    runs = [
        {"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z"},
        {"run_id": "r2", "timestamp_utc": "2026-01-02T00:00:00Z"},
        {"run_id": "r3", "timestamp_utc": "2026-01-03T00:00:00Z"},
    ]
    result = cross_run._build_combo_stability(artifacts, runs, top_n=10)
    assert len(result) == 1

    entry = result[0]
    assert entry["appearances"] == 3
    assert entry["trend_direction"] == "improving"
    assert entry["slope"] > 0
    assert entry["consistency_pct"] == 100.0
    assert entry["return_std"] is not None
    assert entry["sparkline"].startswith("<svg ")
    assert len(entry["trend_points"]) == 3
    assert entry["trend_points"][0]["run_id"] == "r1"
    assert entry["trend_points"][2]["run_id"] == "r3"
    assert entry["trend_points"][0]["oos_return_pct"] == 1.0
    assert entry["trend_points"][2]["oos_return_pct"] == 3.0


def test_build_combo_stability_chronological_order(tmp_path):
    """trend_points should be chronologically ordered even if runs are not."""
    artifacts = tmp_path / "artifacts"
    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct"]
    _write_csv(
        artifacts / "param_sweep_top10_r1.csv", header,
        [{"indicator_list": "a", "regime_name": "b", "vol_mode": "c", "oos_avg_total_return_pct": 10.0}],
    )
    _write_csv(
        artifacts / "param_sweep_top10_r2.csv", header,
        [{"indicator_list": "a", "regime_name": "b", "vol_mode": "c", "oos_avg_total_return_pct": 20.0}],
    )

    # Provide runs in reverse chronological order
    runs = [
        {"run_id": "r2", "timestamp_utc": "2026-02-01T00:00:00Z"},
        {"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z"},
    ]
    result = cross_run._build_combo_stability(artifacts, runs, top_n=10)
    # Should be sorted chronologically: r1 first, r2 second
    assert result[0]["trend_points"][0]["run_id"] == "r1"
    assert result[0]["trend_points"][1]["run_id"] == "r2"


def test_cross_run_payload_combo_stability_has_trend(tmp_path):
    """build_cross_run_payload should include trend fields in combo_stability."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [
                {"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z",
                 "oos_avg_total_return_pct": 1.0, "trade_symbols": ["ETH/USDT"],
                 "timeframes": [{"timeframe": "1h", "days": 90}]},
                {"run_id": "r2", "timestamp_utc": "2026-01-02T00:00:00Z",
                 "oos_avg_total_return_pct": 2.0, "trade_symbols": ["ETH/USDT"],
                 "timeframes": [{"timeframe": "1h", "days": 90}]},
            ],
            "coverage": {},
        }),
        encoding="utf-8",
    )
    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct"]
    _write_csv(
        artifacts / "param_sweep_top10_r1.csv", header,
        [{"indicator_list": "x", "regime_name": "y", "vol_mode": "z", "oos_avg_total_return_pct": 1.0}],
    )
    _write_csv(
        artifacts / "param_sweep_top10_r2.csv", header,
        [{"indicator_list": "x", "regime_name": "y", "vol_mode": "z", "oos_avg_total_return_pct": 2.0}],
    )

    payload = cross_run.build_cross_run_payload(artifacts_dir=artifacts, registry_path=registry_path)
    combo = payload["combo_stability"][0]
    assert "trend_direction" in combo
    assert "trend_points" in combo
    assert "sparkline" in combo
    assert "consistency_pct" in combo


def test_cross_run_html_contains_trend_columns(tmp_path):
    """HTML report should include Combo Stability Trends section with new columns."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [
                {"run_id": "t1", "timestamp_utc": "2026-01-01T00:00:00Z",
                 "oos_avg_total_return_pct": 5.0, "trade_symbols": ["ETH/USDT"]},
            ],
            "coverage": {},
        }),
        encoding="utf-8",
    )
    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct"]
    _write_csv(
        artifacts / "param_sweep_top10_t1.csv", header,
        [{"indicator_list": "a", "regime_name": "b", "vol_mode": "c", "oos_avg_total_return_pct": 5.0}],
    )

    payload = cross_run.build_cross_run_payload(artifacts_dir=artifacts, registry_path=registry_path)
    html = cross_run.render_cross_run_html(payload)
    assert "Combo Stability Trends" in html
    assert "trend" in html.lower()
    assert "consistency_%" in html
    assert "sparkline" in html
    assert "<svg " in html  # sparkline should be embedded


# ---------------------------------------------------------------------------
#  AWF-026: Regime-aware cross-run integration tests
# ---------------------------------------------------------------------------


def test_parse_regime_from_combo_key():
    assert cross_run._parse_regime_from_combo_key("rsi,roc|trend_high|normal") == "trend_high"
    assert cross_run._parse_regime_from_combo_key("mfi|bb_revert_low|high") == "bb_revert_low"
    assert cross_run._parse_regime_from_combo_key("||") == ""
    assert cross_run._parse_regime_from_combo_key("single") == ""


def test_build_per_regime_leaderboard_groups():
    combo_stability = [
        {"combo_key": "a|trend_high|normal", "avg_oos_return_pct": 5.0},
        {"combo_key": "b|trend_high|normal", "avg_oos_return_pct": 10.0},
        {"combo_key": "c|rsi_revert_low|high", "avg_oos_return_pct": 8.0},
        {"combo_key": "d|rsi_revert_low|high", "avg_oos_return_pct": 3.0},
    ]
    result = cross_run._build_per_regime_leaderboard(combo_stability)
    assert "trend_high" in result
    assert "rsi_revert_low" in result
    # trend_high sorted descending: b(10), a(5)
    assert result["trend_high"][0]["combo_key"] == "b|trend_high|normal"
    assert result["trend_high"][1]["combo_key"] == "a|trend_high|normal"
    # rsi_revert_low sorted descending: c(8), d(3)
    assert result["rsi_revert_low"][0]["combo_key"] == "c|rsi_revert_low|high"


def test_build_per_regime_leaderboard_empty():
    assert cross_run._build_per_regime_leaderboard([]) == {}


def test_build_regime_summary():
    combo_stability = [
        {"combo_key": "a|trend_high|n", "avg_oos_return_pct": 10.0, "avg_oos_drawdown_pct": -5.0},
        {"combo_key": "b|trend_high|n", "avg_oos_return_pct": 6.0, "avg_oos_drawdown_pct": -3.0},
        {"combo_key": "c|rsi_revert_low|h", "avg_oos_return_pct": 8.0, "avg_oos_drawdown_pct": -4.0},
    ]
    summary = cross_run._build_regime_summary(combo_stability)
    assert len(summary) == 2
    by_name = {row["regime_name"]: row for row in summary}
    assert by_name["trend_high"]["combo_count"] == 2
    assert by_name["trend_high"]["avg_return_pct"] == 8.0  # (10+6)/2
    assert by_name["trend_high"]["avg_drawdown_pct"] == -4.0  # (-5+-3)/2
    assert by_name["rsi_revert_low"]["combo_count"] == 1
    assert by_name["rsi_revert_low"]["avg_return_pct"] == 8.0


def test_build_regime_summary_empty():
    assert cross_run._build_regime_summary([]) == []


def test_cross_run_payload_has_regime_fields(tmp_path):
    """build_cross_run_payload should include per_regime_leaderboard and regime_summary."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [
                {"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z",
                 "oos_avg_total_return_pct": 2.0, "trade_symbols": ["ETH/USDT"],
                 "timeframes": [{"timeframe": "1h", "days": 90}]},
            ],
            "coverage": {},
        }),
        encoding="utf-8",
    )
    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct"]
    _write_csv(
        artifacts / "param_sweep_top10_r1.csv", header,
        [
            {"indicator_list": "rsi", "regime_name": "trend_high", "vol_mode": "normal",
             "oos_avg_total_return_pct": 5.0},
            {"indicator_list": "mfi", "regime_name": "rsi_revert_low", "vol_mode": "high",
             "oos_avg_total_return_pct": 3.0},
        ],
    )

    payload = cross_run.build_cross_run_payload(artifacts_dir=artifacts, registry_path=registry_path)
    assert "per_regime_leaderboard" in payload
    assert "regime_summary" in payload
    assert "trend_high" in payload["per_regime_leaderboard"]
    assert "rsi_revert_low" in payload["per_regime_leaderboard"]
    assert len(payload["regime_summary"]) == 2


def test_cross_run_html_contains_regime_sections(tmp_path):
    """HTML report should contain Regime Summary and Per-Regime Leaderboard sections."""
    artifacts = tmp_path / "artifacts"
    registry_path = artifacts / "run_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({
            "runs": [
                {"run_id": "rg1", "timestamp_utc": "2026-01-01T00:00:00Z",
                 "oos_avg_total_return_pct": 1.0, "trade_symbols": ["ETH/USDT"]},
            ],
            "coverage": {},
        }),
        encoding="utf-8",
    )
    header = ["indicator_list", "regime_name", "vol_mode", "oos_avg_total_return_pct"]
    _write_csv(
        artifacts / "param_sweep_top10_rg1.csv", header,
        [
            {"indicator_list": "rsi", "regime_name": "trend_high", "vol_mode": "n",
             "oos_avg_total_return_pct": 5.0},
            {"indicator_list": "bb", "regime_name": "bb_revert_low", "vol_mode": "h",
             "oos_avg_total_return_pct": 2.0},
        ],
    )

    payload = cross_run.build_cross_run_payload(artifacts_dir=artifacts, registry_path=registry_path)
    html = cross_run.render_cross_run_html(payload)
    assert "Regime Summary" in html
    assert "Per-Regime Leaderboard" in html
    assert "trend_high" in html
    assert "bb_revert_low" in html

