"""src.strategy.decide.va_breakout — the value-area breakout decider.

The strategy validated in experiments/engine/research (VA breakout in a directional
session): in a session that is directional so far, when a 1m CONSOLIDATION forms and
price breaks its value area IN the session's direction, enter — stop at the opposite
value-area edge, target 2R. Backtested 2015-2025: ~1189 trades, +0.45R, net of costs.

Reads the STRUCTURE reading off the Snapshot (state / strength / vah / val — see
readings/structure.py) and returns an Intent (direction/entry/stop/target) or None.

STATUS: seam wired, logic not ported yet — returns None so DECIDE stays dark in the
monitor until the port (phase 2). The entry rule from research/backtest_equity.py
`collect()` lands here; nothing else in the pipeline moves.
"""
from __future__ import annotations

from ..score import Scores
from ..snapshot import Snapshot
from .base import Decider, Intent, register_decider


@register_decider("va_breakout")
class VaBreakout(Decider):
    def decide(self, snap: Snapshot, scores: Scores) -> "Intent | None":
        # TODO (phase 2): port collect() — read snap.structure {state, strength,
        # vah, val}; if the session is directional (|strength| >= bias_str) and a
        # CONSOLIDATION broke its VA in that direction, return Intent(direction,
        # entry=vah/val, stop=opposite edge, target=2R). For now: no trade.
        return None
