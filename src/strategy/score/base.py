"""src.strategy.score.base — the Score seam: contract + registry.

A Scorer reads a Snapshot's facts and returns Scores (named signals 0..1 +
conviction/direction). Version modules sit beside this file and self-register; the
active one is chosen in config (`strategy.use.scorer`). No scoring logic here —
this only locks the seam so downstream never changes when scoring is filled in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..snapshot import Snapshot


@dataclass
class Scores:
    """Output of a Scorer. `signals` are named 0..1 reads; `conviction` is the
    overall 0..1; `direction` is 'long'/'short'/None. Empty until scoring exists."""
    signals: dict = field(default_factory=dict)
    conviction: float = 0.0
    direction: "str | None" = None

    def to_dict(self) -> dict:
        return {"signals": self.signals, "conviction": self.conviction, "direction": self.direction}


class Scorer:
    """Interface: read a Snapshot's facts -> Scores."""
    def score(self, snap: Snapshot) -> Scores:
        raise NotImplementedError


_REGISTRY: "dict[str, type[Scorer]]" = {}


def register_scorer(name):
    def deco(cls):
        _REGISTRY[name] = cls
        return cls
    return deco


def get_scorer(name: str) -> Scorer:
    if name not in _REGISTRY:
        raise KeyError(f"no scorer '{name}' (have: {sorted(_REGISTRY)})")
    return _REGISTRY[name]()
