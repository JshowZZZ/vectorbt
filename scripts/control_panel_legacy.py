"""Backward-compatibility shim for legacy imports.

AWF-146 migrated control-panel handlers/helpers into responsibility modules.
Importers that still reference ``scripts.control_panel_legacy`` are redirected
to ``scripts.control_panel``.
"""

from importlib import import_module
import sys

_cp = import_module("scripts.control_panel")
sys.modules[__name__] = _cp
