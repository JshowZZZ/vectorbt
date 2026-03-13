from __future__ import annotations

import http.client
import json
import threading
import tempfile
from contextlib import contextmanager
from pathlib import Path

from autowfo.control_panel import server as cp
from autowfo.control_panel import experiments as cp_experiments


def _experiment_config(experiment_id: str) -> dict:
    return {
        "experiment_id": experiment_id,
        "description": "manual validation",
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
                    "param_values": [14],
                    "threshold_values": [30],
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
                    "bb_std_values": [2.0],
                    "pct_values": [0.02],
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
        "wf": {"train_days": 90, "test_days": 30, "step_days": 30},
    }


@contextmanager
def _patched_control_panel_env(temp_root: Path):
    artifacts = temp_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    fields = [
        "ROOT",
        "ARTIFACTS",
        "STATUS_JSON",
        "STATUS_HTML",
        "RUN_LOG",
        "TEST_STATUS_JSON",
        "TEST_LOG",
        "DB_PATH",
        "CONFIG_JSON",
        "CONTROL_JSON",
    ]
    saved = {name: getattr(cp, name) for name in fields}

    cp.ROOT = temp_root
    cp.ARTIFACTS = artifacts
    cp.STATUS_JSON = artifacts / "run_status.json"
    cp.STATUS_HTML = artifacts / "run_status.html"
    cp.RUN_LOG = artifacts / "run_console.log"
    cp.TEST_STATUS_JSON = artifacts / "test_status.json"
    cp.TEST_LOG = artifacts / "test_console.log"
    cp.DB_PATH = artifacts / "results.db"
    cp.CONFIG_JSON = artifacts / "sweep_config.json"
    cp.CONTROL_JSON = artifacts / "run_control.json"

    cp.PROCESS = None
    cp.BATCH_PROCESS = None
    cp.TEST_PROCESS = None
    cp_experiments._scheduler_reset_runtime_state()

    try:
        yield artifacts
    finally:
        cp_experiments._scheduler_reset_runtime_state()
        for name, value in saved.items():
            setattr(cp, name, value)


@contextmanager
def _serve_control_panel(timeout: float = 10.0):
    server = cp.ThreadingHTTPServer(("127.0.0.1", 0), cp.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=timeout)
        yield conn
    finally:
        if conn is not None:
            conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request_json(conn: http.client.HTTPConnection, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    conn.request(method.upper(), path, body=body, headers=headers)
    response = conn.getresponse()
    status = int(response.status)
    raw = response.read().decode("utf-8")
    try:
        data = json.loads(raw)
    except Exception:
        data = {"raw": raw}
    return status, data


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="autowfo_validate_discovery_") as tmp:
        temp_root = Path(tmp)
        with _patched_control_panel_env(temp_root):
            with _serve_control_panel() as conn:
                exp_a = _experiment_config("exp_validate_a")
                exp_b = _experiment_config("exp_validate_b")

                for payload in (exp_a, exp_b):
                    status, data = _request_json(conn, "POST", "/experiments/create", payload)
                    if status != 200 or not data.get("ok"):
                        raise RuntimeError(f"create failed ({status}): {data}")

                for payload in (
                    {"experiment_config": exp_a, "priority": "user_submitted"},
                    {"experiment_config": exp_b, "priority": "user_submitted"},
                ):
                    status, data = _request_json(conn, "POST", "/experiments/queue", payload)
                    if status != 200 or not data.get("ok"):
                        raise RuntimeError(f"queue failed ({status}): {data}")

                status, before = _request_json(conn, "GET", "/scheduler/status.json")
                if status != 200:
                    raise RuntimeError(f"status failed ({status}): {before}")
                if int(before.get("queue_depth", -1)) != 2:
                    raise AssertionError(f"expected queue_depth=2, got: {before}")

                discovery_payload = {
                    "pool_config": {
                        "indicator_ids": ["RSI", "MACD", "EMA"],
                        "combo_size_range": [2, 2],
                        "pruning": {"enabled": False},
                        "priority": "discovery",
                    }
                }
                status, tick = _request_json(conn, "POST", "/discovery/tick", discovery_payload)
                if status != 200 or not tick.get("ok"):
                    raise RuntimeError(f"discovery tick failed ({status}): {tick}")

                status, after = _request_json(conn, "GET", "/scheduler/status.json")
                if status != 200:
                    raise RuntimeError(f"status-after failed ({status}): {after}")

                before_depth = int(before.get("queue_depth", 0))
                after_depth = int(after.get("queue_depth", 0))
                if after_depth <= before_depth:
                    raise AssertionError(
                        f"expected queue depth increase after discovery tick, before={before_depth}, after={after_depth}"
                    )

                summary = {
                    "before_status": before,
                    "tick": tick,
                    "after_status": after,
                    "artifacts": str(cp.ARTIFACTS),
                }
                print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

