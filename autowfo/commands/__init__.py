"""CLI command parser builders split from ``autowfo.cli`` (AWF-114)."""

from .batch import add_batch_parser
from .cron import add_cron_parser
from .gate import add_gate_parser
from .plan import add_plan_parsers
from .run import add_run_parsers

__all__ = [
    "add_batch_parser",
    "add_cron_parser",
    "add_gate_parser",
    "add_plan_parsers",
    "add_run_parsers",
]
