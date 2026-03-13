"""Paper trading position state store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autowfo.storage_contract import PAPER_POSITIONS_SCHEMA_VERSION


POSITION_KEYS = {
    "signal_id",
    "experiment_id",
    "open_ts",
    "open_price",
    "close_ts",
    "close_price",
    "pnl_pct",
    "status",
}


def _as_float(value: Any, field_name: str) -> float:
    try:
        out = float(value)
    except Exception as exc:  # pragma: no cover - simple conversion guard
        raise ValueError(f"{field_name} must be numeric") from exc
    return out


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


class PaperPositionStore:
    def __init__(self, positions_path: str | Path = "artifacts/paper_positions.json"):
        self.positions_path = Path(positions_path)

    @staticmethod
    def _normalize_payload(payload: Any) -> dict:
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("positions", [])
        else:
            rows = []
        out = []
        for row in rows:
            if isinstance(row, dict):
                out.append(dict(row))
        schema_version = (
            str(payload.get("schema_version") or "").strip()
            if isinstance(payload, dict)
            else ""
        ) or PAPER_POSITIONS_SCHEMA_VERSION
        return {"schema_version": schema_version, "positions": out}

    def _load_positions(self) -> list[dict]:
        if not self.positions_path.exists():
            return []
        try:
            payload = json.loads(self.positions_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return []
        return self._normalize_payload(payload)["positions"]

    def _save_positions(self, positions: list[dict]) -> None:
        _atomic_write_json(
            self.positions_path,
            {
                "schema_version": PAPER_POSITIONS_SCHEMA_VERSION,
                "positions": [dict(row) for row in positions if isinstance(row, dict)],
            },
        )

    def list_positions(self) -> list[dict]:
        return self._load_positions()

    def list_open_positions(self) -> list[dict]:
        return [row for row in self._load_positions() if str(row.get("status", "")).strip() == "open"]

    @staticmethod
    def _resolve_mark_price(
        row: dict,
        latest_prices: dict | None,
        latest_closed_by_signal: dict,
        latest_closed_by_experiment: dict,
    ) -> float:
        signal_id = str(row.get("signal_id") or "").strip()
        experiment_id = str(row.get("experiment_id") or "").strip()
        def _try_float(raw):
            try:
                return _as_float(raw, "mark_price")
            except Exception:
                return None
        if isinstance(latest_prices, dict):
            if signal_id in latest_prices:
                parsed = _try_float(latest_prices.get(signal_id))
                if parsed is not None:
                    return parsed
            if experiment_id in latest_prices:
                parsed = _try_float(latest_prices.get(experiment_id))
                if parsed is not None:
                    return parsed
            signal_prices = latest_prices.get("signals")
            if isinstance(signal_prices, dict) and signal_id in signal_prices:
                parsed = _try_float(signal_prices.get(signal_id))
                if parsed is not None:
                    return parsed
            experiment_prices = latest_prices.get("experiments")
            if isinstance(experiment_prices, dict) and experiment_id in experiment_prices:
                parsed = _try_float(experiment_prices.get(experiment_id))
                if parsed is not None:
                    return parsed

        if signal_id in latest_closed_by_signal:
            parsed = _try_float(latest_closed_by_signal.get(signal_id))
            if parsed is not None:
                return parsed
        if experiment_id in latest_closed_by_experiment:
            parsed = _try_float(latest_closed_by_experiment.get(experiment_id))
            if parsed is not None:
                return parsed
        return _as_float(row.get("open_price"), "mark_price")

    def portfolio_snapshot(self, latest_prices: dict | None = None) -> dict:
        positions = self._load_positions()
        latest_closed_by_signal = {}
        latest_closed_by_experiment = {}
        for row in positions:
            if str(row.get("status", "")).strip() != "closed":
                continue
            signal_id = str(row.get("signal_id") or "").strip()
            experiment_id = str(row.get("experiment_id") or "").strip()
            close_price = row.get("close_price")
            if close_price is None:
                continue
            if signal_id:
                latest_closed_by_signal[signal_id] = close_price
            if experiment_id:
                latest_closed_by_experiment[experiment_id] = close_price

        open_rows = []
        total_unrealized = 0.0
        for row in positions:
            if str(row.get("status", "")).strip() != "open":
                continue
            open_price = _as_float(row.get("open_price"), "open_price")
            mark_price = self._resolve_mark_price(
                row=row,
                latest_prices=latest_prices,
                latest_closed_by_signal=latest_closed_by_signal,
                latest_closed_by_experiment=latest_closed_by_experiment,
            )
            pnl_pct = ((mark_price - open_price) / open_price) * 100.0
            enriched = dict(row)
            enriched["mark_price"] = float(mark_price)
            enriched["unrealized_pnl_pct"] = float(pnl_pct)
            total_unrealized += float(pnl_pct)
            open_rows.append(enriched)

        return {
            "positions": open_rows,
            "open_total": len(open_rows),
            "total_unrealized_pnl_pct": float(total_unrealized),
        }

    def open_position(self, signal_id: str, experiment_id: str, open_price: float, open_ts: str) -> dict:
        signal = str(signal_id or "").strip()
        experiment = str(experiment_id or "").strip()
        timestamp = str(open_ts or "").strip()
        if not signal:
            raise ValueError("signal_id is required")
        if not experiment:
            raise ValueError("experiment_id is required")
        if not timestamp:
            raise ValueError("open_ts is required")

        price = _as_float(open_price, "open_price")
        if price <= 0:
            raise ValueError("open_price must be > 0")

        positions = self._load_positions()
        for row in positions:
            if str(row.get("signal_id", "")).strip() == signal and str(row.get("status", "")).strip() == "open":
                raise ValueError("already open")
        record = {
            "signal_id": signal,
            "experiment_id": experiment,
            "open_ts": timestamp,
            "open_price": price,
            "close_ts": None,
            "close_price": None,
            "pnl_pct": None,
            "status": "open",
        }
        positions.append(record)
        self._save_positions(positions)
        return dict(record)

    def close_position(self, signal_id: str, close_price: float, close_ts: str) -> tuple[float, dict]:
        signal = str(signal_id or "").strip()
        timestamp = str(close_ts or "").strip()
        if not signal:
            raise ValueError("signal_id is required")
        if not timestamp:
            raise ValueError("close_ts is required")

        price = _as_float(close_price, "close_price")
        if price <= 0:
            raise ValueError("close_price must be > 0")

        positions = self._load_positions()
        target_idx = None
        for idx in range(len(positions) - 1, -1, -1):
            row = positions[idx]
            if str(row.get("signal_id", "")).strip() == signal and str(row.get("status", "")).strip() == "open":
                target_idx = idx
                break

        if target_idx is None:
            raise ValueError("no open position")

        row = dict(positions[target_idx])
        open_price = _as_float(row.get("open_price"), "open_price")
        pnl_pct = ((price - open_price) / open_price) * 100.0
        row["close_ts"] = timestamp
        row["close_price"] = price
        row["pnl_pct"] = pnl_pct
        row["status"] = "closed"
        positions[target_idx] = row
        self._save_positions(positions)
        return float(pnl_pct), dict(row)

