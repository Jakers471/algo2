"""src.strategy.score.v1 — reference scorer. STUB.

Returns empty scores. TODO: turn snapshot facts into weighted signals once Jake
defines how to measure them and what the weights mean.
"""
from __future__ import annotations

from ..snapshot import Snapshot
from .base import Scorer, Scores, register_scorer


@register_scorer("v1")
class ScorerV1(Scorer):
    def score(self, snap: Snapshot) -> Scores:
        return Scores()
