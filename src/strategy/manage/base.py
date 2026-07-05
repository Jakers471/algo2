"""src.strategy.manage.base — the Manage seam: contract + registry.

A Manager tracks an active Intent across snapshots and emits Actions (arm/
activate/adjust/exit/kill). Version modules sit beside this file and self-register;
the active one is chosen in config (`strategy.use.manager`). Actions are ABSTRACT
verbs — never broker calls — so the strategy stays broker-agnostic (CLAUDE.md #4);
an execution layer later translates Actions into `Broker` interface calls.

TODO (STATE/MEMORY — do not forget): this is the STATEFUL stage. When we build it,
the Manager must own a persistent `book` (open positions + armed intents + running
log) carried ACROSS bars — NOT recomputed each bar. The pipeline gains a driver
that threads one book through every bar (same object in replay/backtest/live) =
the brain's memory. `decide` reads it (avoid double-entry); `manage` mutates it via
Actions. See src/strategy/README.md "State & memory".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..decide import Intent
from ..snapshot import Snapshot


@dataclass
class Action:
    """What to do with a trade this bar: 'none'|'arm'|'activate'|'adjust'|'exit'."""
    kind: str = "none"
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail}


class Manager:
    """Interface: (Intent | None) + Snapshot -> Action."""
    def manage(self, intent: "Intent | None", snap: Snapshot) -> Action:
        raise NotImplementedError


_REGISTRY: "dict[str, type[Manager]]" = {}


def register_manager(name):
    def deco(cls):
        _REGISTRY[name] = cls
        return cls
    return deco


def get_manager(name: str) -> Manager:
    if name not in _REGISTRY:
        raise KeyError(f"no manager '{name}' (have: {sorted(_REGISTRY)})")
    return _REGISTRY[name]()
