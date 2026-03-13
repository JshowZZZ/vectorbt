"""Signal scheduling daemon for auto export + paper position switching."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from autowfo.notifier import NotificationEvent, notify, should_trigger_pnl_threshold
from autowfo.paper_position import PaperPositionStore
from autowfo.signal_exporter import build_live_signal_config_from_combo
from autowfo.storage_contract import SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{time.time_ns()}")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


class SignalScheduler:
    def __init__(
        self,
        analytics_store,
        state_path: str | Path = "artifacts/signal_schedule_state.json",
        export_path: str | Path = "artifacts/live_signal_config.json",
        positions_path: str | Path = "artifacts/paper_positions.json",
        notifier_config_path: str | Path = "artifacts/notifier_config.json",
        schedule_interval_seconds: int = 3600,
        top_n: int = 3,
        max_retries: int = 3,
        backoff_cap_seconds: int = 30,
        now_func: Callable[[], datetime] | None = None,
    ):
        self.analytics_store = analytics_store
        self.state_path = Path(state_path)
        self.export_path = Path(export_path)
        self.positions_path = Path(positions_path)
        self.notifier_config_path = Path(notifier_config_path)
        self.schedule_interval_seconds = max(1, int(schedule_interval_seconds))
        self.top_n = max(1, int(top_n))
        self.max_retries = max(0, int(max_retries))
        self.backoff_cap_seconds = max(1, int(backoff_cap_seconds))
        self._now_func = now_func

    def _default_state(self) -> dict:
        return {
            "schema_version": SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION,
            "tracked_experiment_ids": [],
            "last_experiment_id": None,
            "last_export_ts": "",
            "schedule_interval_seconds": int(self.schedule_interval_seconds),
            "top_n": int(self.top_n),
        }

    def read_state(self) -> dict:
        if not self.state_path.exists():
            return self._default_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        state = self._default_state()
        state["schema_version"] = (
            str(payload.get("schema_version") or "").strip() or SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION
        )
        tracked = payload.get("tracked_experiment_ids")
        if isinstance(tracked, list):
            state["tracked_experiment_ids"] = [str(v).strip() for v in tracked if str(v).strip()]
        elif payload.get("last_experiment_id"):
            state["tracked_experiment_ids"] = [str(payload.get("last_experiment_id")).strip()]
        state["last_experiment_id"] = payload.get("last_experiment_id")
        state["last_export_ts"] = str(payload.get("last_export_ts") or "")
        try:
            state["schedule_interval_seconds"] = max(
                1,
                int(payload.get("schedule_interval_seconds", self.schedule_interval_seconds)),
            )
        except Exception:
            state["schedule_interval_seconds"] = int(self.schedule_interval_seconds)
        try:
            state["top_n"] = max(1, int(payload.get("top_n", self.top_n)))
        except Exception:
            state["top_n"] = int(self.top_n)
        return state

    def write_state(self, state: dict) -> None:
        tracked = state.get("tracked_experiment_ids")
        if not isinstance(tracked, list):
            tracked = []
        tracked = [str(v).strip() for v in tracked if str(v).strip()]
        last_experiment_id = tracked[0] if tracked else None
        payload = {
            "schema_version": SIGNAL_SCHEDULE_STATE_SCHEMA_VERSION,
            "tracked_experiment_ids": tracked,
            "last_experiment_id": state.get("last_experiment_id") or last_experiment_id,
            "last_export_ts": str(state.get("last_export_ts") or ""),
            "schedule_interval_seconds": max(1, int(state.get("schedule_interval_seconds", self.schedule_interval_seconds))),
            "top_n": max(1, int(state.get("top_n", self.top_n))),
        }
        _atomic_write_json(self.state_path, payload)

    def _utc_now(self) -> datetime:
        if self._now_func is not None:
            return self._now_func()
        return datetime.now(timezone.utc)

    @staticmethod
    def _signal_id_for_experiment(experiment_id: str) -> str:
        return f"signal::{str(experiment_id).strip()}"

    @staticmethod
    def _experiment_id_for_signal(signal_id: str) -> str:
        text = str(signal_id or "").strip()
        if text.startswith("signal::"):
            return text.split("::", 1)[1].strip()
        return text

    def _safe_notify(self, event_type: NotificationEvent, payload: dict) -> None:
        try:
            notify(event_type, payload, config_path=self.notifier_config_path)
        except Exception:
            return

    def _ranked_rows(self) -> list[dict]:
        limit_n = max(self.top_n * 5, self.top_n)
        rows = self.analytics_store.query_all_time_best(limit=limit_n)
        deduped = []
        seen_experiments = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            exp_id = str(row.get("experiment_id") or "").strip()
            if not exp_id or exp_id in seen_experiments:
                continue
            seen_experiments.add(exp_id)
            deduped.append(row)
            if len(deduped) >= self.top_n:
                break
        return deduped

    def _write_export(self, top_row: dict) -> dict:
        payload = build_live_signal_config_from_combo(top_row)
        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def tick(self) -> dict:
        rows = self._ranked_rows()
        if not rows:
            return {
                "ok": True,
                "action": "skip_no_strategy",
                "changed": False,
                "tracked_experiment_ids": [],
            }

        top_row = rows[0]
        top_experiment_id = str(top_row.get("experiment_id") or "").strip()
        if not top_experiment_id:
            return {
                "ok": True,
                "action": "skip_invalid_strategy",
                "changed": False,
                "tracked_experiment_ids": [],
            }

        state = self.read_state()
        tracked_experiment_ids = state.get("tracked_experiment_ids")
        if not isinstance(tracked_experiment_ids, list):
            tracked_experiment_ids = []
        tracked_experiment_ids = [str(v).strip() for v in tracked_experiment_ids if str(v).strip()]
        previous_experiment_id = str(tracked_experiment_ids[0] if tracked_experiment_ids else "").strip()
        target_experiment_ids = [str(row.get("experiment_id") or "").strip() for row in rows if str(row.get("experiment_id") or "").strip()]
        now_iso = self._utc_now().replace(microsecond=0).isoformat()

        if tracked_experiment_ids == target_experiment_ids:
            state["schedule_interval_seconds"] = int(self.schedule_interval_seconds)
            state["top_n"] = int(self.top_n)
            state["tracked_experiment_ids"] = target_experiment_ids
            state["last_experiment_id"] = target_experiment_ids[0] if target_experiment_ids else None
            self.write_state(state)
            return {
                "ok": True,
                "action": "skip_same_strategy",
                "changed": False,
                "experiment_id": top_experiment_id,
                "tracked_experiment_ids": target_experiment_ids,
            }

        position_store = PaperPositionStore(self.positions_path)
        open_positions = position_store.list_positions()
        open_by_experiment = {}
        for row in open_positions:
            if str(row.get("status") or "").strip() != "open":
                continue
            exp_id = self._experiment_id_for_signal(row.get("signal_id"))
            if exp_id:
                open_by_experiment[exp_id] = dict(row)

        dropped_experiment_ids = [exp for exp in tracked_experiment_ids if exp not in target_experiment_ids]
        new_experiment_ids = [exp for exp in target_experiment_ids if exp not in tracked_experiment_ids]
        closed_positions = []
        opened_positions = []

        for exp_id in dropped_experiment_ids:
            signal_id = self._signal_id_for_experiment(exp_id)
            try:
                pnl_pct, closed_record = position_store.close_position(
                    signal_id=signal_id,
                    close_price=1.0,
                    close_ts=now_iso,
                )
                closed_positions.append({"signal_id": signal_id, "experiment_id": exp_id, "pnl_pct": pnl_pct})
                self._safe_notify(
                    NotificationEvent.POSITION_CLOSED,
                    {
                        "signal_id": signal_id,
                        "experiment_id": exp_id,
                        "close_ts": now_iso,
                        "pnl_pct": pnl_pct,
                        "status": str(closed_record.get("status") or ""),
                    },
                )
                if should_trigger_pnl_threshold(pnl_pct, config_path=self.notifier_config_path):
                    self._safe_notify(
                        NotificationEvent.PNL_THRESHOLD_HIT,
                        {
                            "signal_id": signal_id,
                            "experiment_id": exp_id,
                            "close_ts": now_iso,
                            "pnl_pct": pnl_pct,
                        },
                    )
            except Exception as exc:
                closed_positions.append({"signal_id": signal_id, "experiment_id": exp_id, "error": str(exc)})

        top_row_map = {str(row.get("experiment_id") or "").strip(): row for row in rows}
        for exp_id in new_experiment_ids:
            signal_id = self._signal_id_for_experiment(exp_id)
            if exp_id in open_by_experiment:
                continue
            try:
                open_record = position_store.open_position(
                    signal_id=signal_id,
                    experiment_id=exp_id,
                    open_price=1.0,
                    open_ts=now_iso,
                )
                opened_positions.append({"signal_id": signal_id, "experiment_id": exp_id})
                self._safe_notify(
                    NotificationEvent.POSITION_OPENED,
                    {
                        "signal_id": signal_id,
                        "experiment_id": exp_id,
                        "open_ts": now_iso,
                        "open_price": 1.0,
                        "status": str(open_record.get("status") or ""),
                    },
                )
            except Exception as exc:
                opened_positions.append({"signal_id": signal_id, "experiment_id": exp_id, "error": str(exc)})

        export_payload = self._write_export(top_row)
        self._safe_notify(
            NotificationEvent.STRATEGY_CHANGED,
            {
                "previous_experiment_ids": tracked_experiment_ids,
                "current_experiment_ids": target_experiment_ids,
                "previous_top_experiment_id": previous_experiment_id or None,
                "current_top_experiment_id": top_experiment_id,
                "changed_utc": now_iso,
            },
        )

        state["tracked_experiment_ids"] = target_experiment_ids
        state["last_experiment_id"] = top_experiment_id
        state["last_export_ts"] = now_iso
        state["schedule_interval_seconds"] = int(self.schedule_interval_seconds)
        state["top_n"] = int(self.top_n)
        self.write_state(state)

        close_result = {
            "attempted": bool(dropped_experiment_ids),
            "closed": bool(any("error" not in row for row in closed_positions)),
            "error": "",
        }
        if any("error" in row for row in closed_positions):
            close_result["error"] = "; ".join(str(row.get("error") or "") for row in closed_positions if row.get("error"))
        open_signal_id = ""
        for row in opened_positions:
            if row.get("signal_id") and "error" not in row:
                open_signal_id = str(row["signal_id"])
                break

        return {
            "ok": True,
            "action": "switched_strategy",
            "changed": True,
            "previous_experiment_id": previous_experiment_id or None,
            "experiment_id": top_experiment_id,
            "previous_experiment_ids": tracked_experiment_ids,
            "tracked_experiment_ids": target_experiment_ids,
            "top_n": int(self.top_n),
            "opened_positions": opened_positions,
            "closed_positions": closed_positions,
            "close_result": close_result,
            "open_signal_id": open_signal_id or None,
            "export_path": str(self.export_path),
            "export_experiment_id": export_payload.get("experiment_id"),
        }

    def _tick_with_retry(self, sleep_func: Callable[[float], None]) -> dict:
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                result = self.tick()
                if attempt > 0:
                    result = dict(result)
                    result["retry_attempts"] = int(attempt)
                return result
            except Exception as exc:
                last_error = str(exc)
                if attempt >= self.max_retries:
                    break
                wait_seconds = min(float(2 ** attempt), float(self.backoff_cap_seconds))
                sleep_func(wait_seconds)

        self._safe_notify(
            NotificationEvent.PATROL_ANOMALY,
            {
                "component": "signal_scheduler",
                "error": last_error,
                "max_retries": int(self.max_retries),
                "occurred_utc": self._utc_now().replace(microsecond=0).isoformat(),
            },
        )
        return {
            "ok": False,
            "action": "tick_error",
            "error": last_error,
            "retry_attempts": int(self.max_retries),
        }

    def run_forever(self, max_ticks: int | None = None, sleep_func: Callable[[float], None] = time.sleep) -> int:
        tick_count = 0
        while True:
            self._tick_with_retry(sleep_func=sleep_func)
            tick_count += 1
            if max_ticks is not None and tick_count >= int(max_ticks):
                break
            sleep_func(float(self.schedule_interval_seconds))
        return tick_count

