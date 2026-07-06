"""src.strategy.manage.book — the persistent state (the brain's memory).

Facts are recomputed from bars every bar (stateless); POSITIONS and DECISIONS are
not — they exist because of a past decision and must persist ACROSS bars. That
memory lives here: the open `Position`, the `traded` fingerprints (so we take a
base's break ONCE, like the backtest), and a `log` of closed trades.

A Driver (src.strategy.pipeline) threads ONE Book through every bar — the same
object in replay / backtest / live. `manage` mutates it; nothing else does.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    direction: str          # 'long' | 'short'
    entry: float
    stop: float
    target: float
    risk: float             # abs(entry - stop) — 1R in price
    opened_asof: int

    def to_dict(self) -> dict:
        return {"direction": self.direction, "entry": self.entry, "stop": self.stop,
                "target": self.target, "risk": self.risk, "opened_asof": self.opened_asof}


@dataclass
class Book:
    position: "Position | None" = None
    traded: list = field(default_factory=list)   # (entry,stop) fingerprints already taken
    log: list = field(default_factory=list)      # closed trades: dir/entry/exit/R/reason/asofs

    def realized_R(self) -> float:
        return round(sum(t["R"] for t in self.log), 2)

    def to_dict(self) -> dict:
        return {
            "position": self.position.to_dict() if self.position else None,
            "closed": len(self.log),
            "realized_R": self.realized_R(),
            "last": self.log[-1] if self.log else None,
        }
