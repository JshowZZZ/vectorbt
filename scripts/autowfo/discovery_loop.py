"""Mode-B discovery loop orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from scripts.autowfo.experiment import Experiment
from scripts.autowfo.pool_discovery import generate_combinations


def _as_str_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            return [text]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return []


class DiscoveryLoop:
    def __init__(
        self,
        pool_config: dict,
        scheduler,
        analytics_store,
        experiments_root: str | Path = "artifacts/experiments",
    ):
        self.pool_config = dict(pool_config or {})
        self.scheduler = scheduler
        self.analytics_store = analytics_store
        self.experiments_root = Path(experiments_root)

    def _top_indicators(self) -> list[str]:
        limit = int(self.pool_config.get("leaderboard_limit", 20) or 20)
        try:
            rows = self.analytics_store.query_indicator_leaderboard(limit=limit)
        except Exception:
            rows = []

        ordered = []
        seen = set()
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            values = _as_str_list(row.get("trigger_indicators")) + _as_str_list(row.get("action_indicators"))
            for item in values:
                if not item or item in seen:
                    continue
                seen.add(item)
                ordered.append(item)
        return ordered

    def _resolve_indicator_pool(self) -> list[str]:
        configured = _as_str_list(self.pool_config.get("indicator_ids") or self.pool_config.get("indicator_pool"))
        top = self._top_indicators()
        if configured and top:
            top_set = set(top)
            filtered = [item for item in configured if item in top_set]
            return filtered or configured
        if configured:
            return configured
        return top

    def _is_analytics_cold_start(self) -> bool:
        return len(self._top_indicators()) == 0

    def _existing_experiment_ids(self) -> set[str]:
        ids = set()
        try:
            ids.update(set(self.scheduler.experiment_ids()))
        except Exception:
            pass

        if self.experiments_root.exists():
            for cfg_path in self.experiments_root.glob("*/config.json"):
                try:
                    payload = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                exp_id = str(payload.get("experiment_id") or cfg_path.parent.name).strip()
                if exp_id:
                    ids.add(exp_id)
        return ids

    def tick(self) -> dict:
        cold_start = self._is_analytics_cold_start()
        if cold_start:
            indicator_pool = _as_str_list(self.pool_config.get("indicator_ids") or self.pool_config.get("indicator_pool"))
            if indicator_pool:
                logging.warning("analytics cold-start: using full pool expansion")
        else:
            indicator_pool = self._resolve_indicator_pool()
        if len(indicator_pool) < 2:
            return {
                "generated": 0,
                "enqueued": 0,
                "skipped_existing": 0,
                "queue_depth": int(self.scheduler.size()),
            }

        cfg = dict(self.pool_config)
        cfg["indicator_ids"] = indicator_pool
        if cold_start:
            pruning_cfg = dict(cfg.get("pruning", {}) or {})
            pruning_cfg["enabled"] = False
            cfg["pruning"] = pruning_cfg
            generated = generate_combinations(cfg, analytics_store=None)
        else:
            generated = generate_combinations(cfg, analytics_store=self.analytics_store)

        existing_ids = self._existing_experiment_ids()
        enqueued = 0
        skipped_existing = 0
        priority = str(self.pool_config.get("priority", "discovery") or "discovery")
        for experiment_cfg in generated:
            try:
                experiment = Experiment.from_dict(experiment_cfg)
            except Exception:
                skipped_existing += 1
                continue
            exp_id = str(experiment.experiment_id).strip()
            if not exp_id or exp_id in existing_ids:
                skipped_existing += 1
                continue
            if self.scheduler.add(dict(experiment.config), priority=priority):
                existing_ids.add(exp_id)
                enqueued += 1
            else:
                skipped_existing += 1

        return {
            "generated": len(generated),
            "enqueued": enqueued,
            "skipped_existing": skipped_existing,
            "queue_depth": int(self.scheduler.size()),
        }
