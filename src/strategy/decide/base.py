"""src.strategy.decide.base — the Decide seam: contract + registry.

A Decider reads a Snapshot + Scores and returns an Intent (direction/entry/stop/
target) or None (no trade this bar). Version modules sit beside this file and
self-register; the active one is chosen in config (`strategy.use.decider`). No
rules here — this only locks the seam.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..score import Scores
from ..snapshot import Snapshot


@dataclass
class Intent:
    """A proposed trade. A None-returning decider means no trade this bar."""
    direction: str          # 'long' | 'short'
    entry: float
    stop: float
    target: float

    def to_dict(self) -> dict:
        return {"direction": self.direction, "entry": self.entry, "stop": self.stop, "target": self.target}


class Decider:
    """Interface: Snapshot + Scores -> Intent | None."""
    def decide(self, snap: Snapshot, scores: Scores) -> "Intent | None":
        raise NotImplementedError


_REGISTRY: "dict[str, type[Decider]]" = {}


def register_decider(name):
    def deco(cls):
        _REGISTRY[name] = cls
        return cls
    return deco


def get_decider(name: str) -> Decider:
    if name not in _REGISTRY:
        raise KeyError(f"no decider '{name}' (have: {sorted(_REGISTRY)})")
    return _REGISTRY[name]()
