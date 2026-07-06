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

# Strategy knobs (from the research; TODO move to algo_config.yaml, convention #3).
BIAS_STR = 0.3      # |L1 strength| to call the session directional (the bias filter)
TARGET_R = 2.0      # profit target in R (VA-height multiples); stop = opposite VA edge


@register_decider("va_breakout")
class VaBreakout(Decider):
    """VA breakout in a directional session (ported from research/backtest_equity.py
    `collect()`). Reads two scales off the Snapshot: L1 `structure.strength` = the
    session bias, L2 `consolidation` = the tradeable base. When the session is
    directional AND price has broken the base's value area IN that direction, propose
    the trade: entry at the broken edge, stop at the opposite edge (risk = VA height),
    target TARGET_R. Fires whenever the setup holds; `manage`/the book gate re-entry."""

    def decide(self, snap: Snapshot, scores: Scores) -> "Intent | None":
        stc = snap.structure or {}
        cons = snap.consolidation or {}
        strength = stc.get("strength")
        vah, val, price = cons.get("vah"), cons.get("val"), snap.price
        if strength is None or vah is None or val is None or vah <= val:
            return None
        risk = vah - val
        if strength >= BIAS_STR and price > vah:          # bull session + upside break
            return Intent("long", entry=vah, stop=val, target=vah + TARGET_R * risk)
        if strength <= -BIAS_STR and price < val:         # bear session + downside break
            return Intent("short", entry=val, stop=vah, target=val - TARGET_R * risk)
        return None
