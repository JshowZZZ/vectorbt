import json
from pathlib import Path

from scripts.autowfo import cross_run


def _write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(row.get(col, "")) for col in header))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
