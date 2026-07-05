"""src.strategy.manage.fixed — fixed-stop manager. STUB.

Does nothing yet. TODO: fixed-stop lifecycle (arm on intent, activate on fill,
exit at fixed stop/target).
"""
from __future__ import annotations

from ..decide import Intent
from ..snapshot import Snapshot
from .base import Action, Manager, register_manager


@register_manager("fixed")
class FixedManager(Manager):
    def manage(self, intent: "Intent | None", snap: Snapshot) -> Action:
        return Action()
