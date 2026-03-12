"""Compatibility shim for legacy `autowfo.cli_legacy` imports."""

from importlib import import_module
import sys

_cli = import_module("autowfo.cli")
sys.modules[__name__] = _cli

