"""Combo intelligent pruning ??adaptive score-based filtering for search acceleration.

AWF-022: Track per-indicator contribution scores during search and prune combos
whose expected score falls below a running threshold.  Works with both serial and
parallel (batch) evaluation modes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Default pruning configuration
# ---------------------------------------------------------------------------

def _default_pruning_config() -> Dict[str, Any]:
    """Return the default pruning configuration dict.

    Keys
    ----
    enabled : bool
        Master switch.  When *False* the tracker is inert (``should_prune``
        always returns *False*).
    warmup_count : int
        Minimum number of evaluated combos before pruning activates.
        A smaller value prunes sooner but risks cutting good combos.
    prune_ratio : float
        A combo is pruned when its predicted score is below
        ``top_threshold * prune_ratio``.  0.0 disables score pruning.
        0.3 = prune combos predicted to score < 30 % of current top median.
    batch_size : int
        Number of tasks per parallel batch.  After each batch the tracker
        updates its thresholds.  Larger batches = fewer updates but more
        stable estimates.
    max_combos_evaluated : int
        Hard budget cap.  0 = unlimited.
    top_n_track : int
        Number of top results to maintain for threshold computation.
    indicator_min_samples : int
        Minimum observations per indicator before its score is trusted
        for pruning decisions.
    """
    return {
        "enabled": True,
        "warmup_count": 500,
        "prune_ratio": 0.3,
        "batch_size": 2000,
        "max_combos_evaluated": 0,
        "top_n_track": 50,
        "indicator_min_samples": 20,
    }


# ---------------------------------------------------------------------------
# PruningTracker
# ---------------------------------------------------------------------------

class PruningTracker:
    """Stateful tracker that accumulates per-indicator scores and decides
    whether a combo should be pruned.

    Thread-safety: **not** thread-safe.  Designed to be used from the main
    process that orchestrates result collection (never inside worker
    processes).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = _default_pruning_config()
        if config:
            cfg.update(config)
        self.enabled: bool = bool(cfg["enabled"])
        self.warmup_count: int = int(cfg["warmup_count"])
        self.prune_ratio: float = float(cfg["prune_ratio"])
        self.batch_size: int = int(cfg["batch_size"])
        self.max_combos_evaluated: int = int(cfg["max_combos_evaluated"])
        self.top_n_track: int = int(cfg["top_n_track"])
        self.indicator_min_samples: int = int(cfg["indicator_min_samples"])

        # --- mutable state ---
        self._evaluated_count: int = 0
        self._pruned_count: int = 0
        # per-indicator running stats: key ??list of scores
        self._indicator_scores: Dict[str, List[float]] = defaultdict(list)
        # top-N scores seen so far (sorted descending, capped at top_n_track)
        self._top_scores: List[float] = []
        # cached threshold (updated after each batch)
        self._score_threshold: float = -math.inf

    # ----- warm-start from existing results -----

    def warm_start(self, existing_combo_df, score_column: str = "oos_avg_total_return_pct") -> None:
        """Seed the tracker with scores from a previous run's results.

        Parameters
        ----------
        existing_combo_df : pd.DataFrame
            Previous combo results.  Must contain *score_column* and
            ``indicator_list`` columns.
        score_column : str
            Column to use as the score metric.
        """
        if existing_combo_df is None or existing_combo_df.empty:
            return
        if score_column not in existing_combo_df.columns:
            return
        if "indicator_list" not in existing_combo_df.columns:
            return

        for _, row in existing_combo_df.iterrows():
            score = row.get(score_column)
            if score is None or (isinstance(score, float) and math.isnan(score)):
                continue
            score = float(score)
            indicator_list = str(row.get("indicator_list", ""))
            indicators = [v.strip() for v in indicator_list.split(",") if v.strip()]
            if not indicators:
                continue
            for ind in indicators:
                self._indicator_scores[ind].append(score)
            self._evaluated_count += 1
            self._insert_top_score(score)

        self._update_threshold()

    # ----- recording results -----

    def record_result(
        self,
        indicator_combo: Sequence[str],
        score: float,
    ) -> None:
        """Record the score of one evaluated combo.

        Call this from the main process after each combo result is available.
        """
        if score is None or (isinstance(score, float) and math.isnan(score)):
            score = 0.0
        self._evaluated_count += 1
        for ind in indicator_combo:
            self._indicator_scores[ind].append(score)
        self._insert_top_score(score)

    def update_threshold(self) -> None:
        """Recompute the pruning threshold from accumulated top scores.

        Typically called once per batch boundary.
        """
        self._update_threshold()

    # ----- pruning decisions -----

    def should_prune(self, indicator_combo: Sequence[str]) -> bool:
        """Return *True* if *indicator_combo* should be skipped.

        Pruning activates only when:
        1. ``enabled`` is *True*
        2. Enough combos have been evaluated (``>= warmup_count``)
        3. Each indicator in the combo has enough samples
           (``>= indicator_min_samples``)
        4. The predicted score is below ``score_threshold * prune_ratio``
        """
        if not self.enabled:
            return False
        if self.prune_ratio <= 0.0:
            return False
        if self._evaluated_count < self.warmup_count:
            return False
        predicted = self._predict_score(indicator_combo)
        if predicted is None:
            return False  # not enough data ??don't prune
        return predicted < self._score_threshold

    def budget_exhausted(self) -> bool:
        """Return *True* if the hard evaluation budget has been reached."""
        if self.max_combos_evaluated <= 0:
            return False
        return self._evaluated_count >= self.max_combos_evaluated

    # ----- statistics -----

    @property
    def evaluated_count(self) -> int:
        return self._evaluated_count

    @property
    def pruned_count(self) -> int:
        return self._pruned_count

    def increment_pruned(self) -> None:
        self._pruned_count += 1

    @property
    def score_threshold(self) -> float:
        return self._score_threshold

    def summary(self) -> Dict[str, Any]:
        """Return a summary dict suitable for logging / serialization."""
        return {
            "evaluated": self._evaluated_count,
            "pruned": self._pruned_count,
            "score_threshold": self._score_threshold,
            "top_scores_len": len(self._top_scores),
            "indicator_count": len(self._indicator_scores),
            "enabled": self.enabled,
        }

    # ----- internals -----

    def _predict_score(self, indicator_combo: Sequence[str]) -> Optional[float]:
        """Predict the expected score of a combo from per-indicator averages.

        Returns *None* when there is insufficient data for any indicator
        in the combo.
        """
        total = 0.0
        count = 0
        for ind in indicator_combo:
            scores = self._indicator_scores.get(ind)
            if scores is None or len(scores) < self.indicator_min_samples:
                return None
            total += sum(scores) / len(scores)
            count += 1
        if count == 0:
            return None
        return total / count

    def _insert_top_score(self, score: float) -> None:
        """Insert *score* into the top-N sorted list."""
        import bisect
        bisect.insort(self._top_scores, score)
        if len(self._top_scores) > self.top_n_track:
            self._top_scores.pop(0)  # remove smallest

    def _update_threshold(self) -> None:
        """Recompute ``_score_threshold`` from the current top scores."""
        if not self._top_scores:
            self._score_threshold = -math.inf
            return
        # Use the median of top-N as the reference
        mid = len(self._top_scores) // 2
        median_top = self._top_scores[mid]
        self._score_threshold = median_top * self.prune_ratio


# ---------------------------------------------------------------------------
# Batch splitting utility
# ---------------------------------------------------------------------------

def _split_into_batches(
    items: list,
    batch_size: int,
) -> List[list]:
    """Split *items* into sub-lists of at most *batch_size*."""
    if batch_size <= 0:
        return [items] if items else []
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

