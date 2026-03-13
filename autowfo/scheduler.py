"""Queue scheduler primitives for Phase-23 discovery execution."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autowfo.storage_contract import SCHEDULER_QUEUE_SCHEMA_VERSION


@dataclass
class SchedulerConfig:
    priority_order: list[str]
    max_concurrent: int
    schedule_cron: str

    @classmethod
    def from_file(cls, path: str | Path = "artifacts/scheduler.json") -> "SchedulerConfig":
        cfg_path = Path(path)
        if cfg_path.exists():
            try:
                payload = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            except Exception:
                payload = {}
        else:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        priority_order = payload.get("priority_order")
        if not isinstance(priority_order, list) or not priority_order:
            priority_order = ["user_submitted", "discovery", "refine"]
        priority_order = [str(item).strip() for item in priority_order if str(item).strip()]
        if not priority_order:
            priority_order = ["user_submitted", "discovery", "refine"]
        try:
            max_concurrent = max(1, int(payload.get("max_concurrent", 1)))
        except Exception:
            max_concurrent = 1
        schedule_cron = str(payload.get("schedule_cron", "") or "").strip()
        return cls(
            priority_order=priority_order,
            max_concurrent=max_concurrent,
            schedule_cron=schedule_cron,
        )


class ExperimentQueue:
    def __init__(
        self,
        queue_path: str | Path = "artifacts/scheduler_queue.json",
        config: SchedulerConfig | None = None,
    ):
        self.queue_path = Path(queue_path)
        self.config = config or SchedulerConfig.from_file()
        self._state = self._load_state()

    def _default_state(self) -> dict:
        return {
            "schema_version": SCHEDULER_QUEUE_SCHEMA_VERSION,
            "version": 1,
            "next_seq": 1,
            "items": [],
            "updated_utc": "",
        }

    def _load_state(self) -> dict:
        if not self.queue_path.exists():
            return self._default_state()
        try:
            payload = json.loads(self.queue_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        if not isinstance(payload.get("items"), list):
            payload["items"] = []
        try:
            payload["next_seq"] = max(1, int(payload.get("next_seq", 1)))
        except Exception:
            payload["next_seq"] = 1
        payload.setdefault("schema_version", SCHEDULER_QUEUE_SCHEMA_VERSION)
        payload.setdefault("version", 1)
        return payload

    def _priority_rank(self, priority: str) -> int:
        p = str(priority or "").strip()
        try:
            return self.config.priority_order.index(p)
        except ValueError:
            return len(self.config.priority_order)

    def _persist(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self._state["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp_path = self.queue_path.with_suffix(
            f"{self.queue_path.suffix}.tmp.{os.getpid()}.{time.time_ns()}"
        )
        try:
            tmp_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self.queue_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def add(self, experiment_config: dict, priority: str) -> bool:
        if not isinstance(experiment_config, dict):
            raise ValueError("experiment_config must be dict")
        experiment_id = str(experiment_config.get("experiment_id", "")).strip()
        if not experiment_id:
            raise ValueError("experiment_config.experiment_id is required")
        if self.contains(experiment_id):
            return False
        seq = int(self._state["next_seq"])
        self._state["next_seq"] = seq + 1
        self._state["items"].append(
            {
                "experiment_id": experiment_id,
                "priority": str(priority or "").strip() or "discovery",
                "seq": seq,
                "experiment_config": experiment_config,
            }
        )
        self._persist()
        return True

    def _best_index(self) -> int | None:
        items = self._state.get("items", [])
        if not items:
            return None
        best_idx = 0
        best_key = (
            self._priority_rank(items[0].get("priority", "")),
            int(items[0].get("seq", 0)),
        )
        for idx, item in enumerate(items[1:], start=1):
            key = (
                self._priority_rank(item.get("priority", "")),
                int(item.get("seq", 0)),
            )
            if key < best_key:
                best_key = key
                best_idx = idx
        return best_idx

    def pop(self) -> dict | None:
        idx = self._best_index()
        if idx is None:
            return None
        item = self._state["items"].pop(idx)
        self._persist()
        return item

    def peek(self) -> dict | None:
        idx = self._best_index()
        if idx is None:
            return None
        return dict(self._state["items"][idx])

    def size(self) -> int:
        return len(self._state.get("items", []))

    def contains(self, experiment_id: str) -> bool:
        target = str(experiment_id).strip()
        return any(str(item.get("experiment_id", "")).strip() == target for item in self._state.get("items", []))

    def experiment_ids(self) -> set[str]:
        return {
            str(item.get("experiment_id", "")).strip()
            for item in self._state.get("items", [])
            if str(item.get("experiment_id", "")).strip()
        }

    def snapshot(self) -> dict:
        return dict(self._state)

    def rewrite_state(self) -> None:
        self._persist()

