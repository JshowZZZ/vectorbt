"""Public engine facade.

AWF-115: only public constants stay here; private orchestration helpers live in
their source modules (`engine_helpers`, `engine_runtime`, `engine_search`,
`engine_report`, `engine_finalize`).
"""

from .engine_helpers import DEFAULT_CONFIG

__all__ = ["DEFAULT_CONFIG"]

