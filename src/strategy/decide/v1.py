"""src.strategy.decide.v1 — reference decider. STUB.

Never trades yet. TODO: turn scores into an intent once Jake defines the rules
(thresholds, how entry/stop/target are formed).
"""
from __future__ import annotations

from ..score import Scores
from ..snapshot import Snapshot
from .base import Decider, Intent, register_decider


@register_decider("v1")
class DeciderV1(Decider):
    def decide(self, snap: Snapshot, scores: Scores) -> "Intent | None":
        return None
