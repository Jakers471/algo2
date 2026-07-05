"""src.strategy.manage.trailing — trailing-stop manager. STUB.

Does nothing yet. TODO: trailing-stop lifecycle (trail the stop behind price as it
moves in favor).
"""
from __future__ import annotations

from ..decide import Intent
from ..snapshot import Snapshot
from .base import Action, Manager, register_manager


@register_manager("trailing")
class TrailingManager(Manager):
    def manage(self, intent: "Intent | None", snap: Snapshot) -> Action:
        return Action()
