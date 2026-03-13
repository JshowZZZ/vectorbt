"""Indicator plugin auto-discovery for AUTOWFO."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from types import ModuleType
from typing import Dict

REGISTRY: Dict[str, ModuleType] = {}
_logger = logging.getLogger(__name__)


def _discover() -> None:
    """Discover indicator modules in this package and build REGISTRY."""
    REGISTRY.clear()
    pkg_dir = Path(__file__).parent
    importlib.invalidate_caches()
    for path in sorted(pkg_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"{__name__}.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            indicator_id = getattr(mod, "INDICATOR_ID", None)
            if indicator_id:
                REGISTRY[indicator_id] = mod
        except Exception as exc:  # pragma: no cover - exercised by integration-style test
            _logger.warning("Failed to load indicator plugin %s: %s", path.name, exc)


_discover()


