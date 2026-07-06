"""src.strategy.manage.fixed — fixed stop/target lifecycle (the baseline manager).

Turns decide's repeated Intents into ONE managed trade:
  - FLAT + Intent for a base we haven't taken -> enter (record the Position, fingerprint
    the base so we never re-enter it — one trade per base, like the backtest). Action 'activate'.
  - IN a position -> hold; exit when price reaches the stop or target (fill AT the level,
    R = -1 / +2). Action 'active' while holding, 'exit' on close-out. New Intents are
    ignored while in a trade (no double-entry).
  - else -> 'none'.

Honors the Intent's own stop/target (decide sets stop = opposite VA edge = 1R, target 2R),
matching backtest_equity's 2R-hard-stop rule. Exit uses the bar CLOSE (snap.price); the
backtest driver (phase 5) will feed intrabar high/low for exact fills.
"""
from __future__ import annotations

from ..decide import Intent
from ..snapshot import Snapshot
from .base import Action, Manager, register_manager
from .book import Book, Position


@register_manager("fixed")
class FixedManager(Manager):
    def manage(self, intent: "Intent | None", snap: Snapshot, book: Book) -> Action:
        price = snap.price
        pos = book.position

        if pos is not None:                                   # --- managing an open trade ---
            long = pos.direction == "long"
            hit_stop = price <= pos.stop if long else price >= pos.stop
            hit_tgt = price >= pos.target if long else price <= pos.target
            if hit_stop or hit_tgt:
                exit_px = pos.stop if hit_stop else pos.target
                R = round((exit_px - pos.entry) / pos.risk * (1 if long else -1), 2)
                book.log.append({"direction": pos.direction, "entry": pos.entry,
                                 "exit": exit_px, "R": R, "reason": "stop" if hit_stop else "target",
                                 "opened_asof": pos.opened_asof, "closed_asof": snap.asof})
                book.position = None
                return Action("exit", {"direction": pos.direction, "exit": exit_px,
                                       "R": R, "reason": "stop" if hit_stop else "target"})
            unreal = round((price - pos.entry) / pos.risk * (1 if long else -1), 2)
            return Action("active", {"direction": pos.direction, "entry": pos.entry,
                                     "stop": pos.stop, "target": pos.target, "unreal_R": unreal})

        if intent is not None:                                # --- flat: consider entering ---
            sig = (round(intent.entry, 1), round(intent.stop, 1))   # this base's fingerprint
            if sig in book.traded:
                return Action("none")                          # already took this base's break
            book.traded.append(sig)
            book.position = Position(intent.direction, intent.entry, intent.stop, intent.target,
                                     abs(intent.entry - intent.stop), snap.asof)
            return Action("activate", {"direction": intent.direction, "entry": intent.entry,
                                       "stop": intent.stop, "target": intent.target})
        return Action("none")
