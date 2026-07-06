"""src.strategy.readings.structure — facts from the GRADE engine.

Reads the one measurement `grade()` (experiments/engine/grade.py, spec:
experiments/GRADE_SPEC.md) on the current bar window and derives the structural
facts the VA-breakout strategy actually looks at: the regime `state`, the
directional `strength`, and the value-area levels `poc/vah/val`. Facts only — no
opinions (that's `score`'s job), no trade decisions (that's `decide`'s job).

This is the bridge GRADE_SPEC §7 named: the spec is the "fact layer"; turning those
facts into trades is downstream. Here the facts enter the pipeline's Snapshot.

TODO (engine location): `grade()` still lives under experiments/engine while it is
the frozen research core. It is pure OHLCV-in/values-out (belongs in src/ long term);
until it graduates, we add that folder to the path. Only THIS import moves when it does.
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_REPO, "experiments", "engine"))
from grade import grade  # noqa: E402


def read_structure(df) -> dict | None:
    """OHLCV slice (the current window) -> the structural reading, or None if empty.

    `{state, direction, strength, efficiency, acceptance, poc, vah, val}` — the
    GRADE fields the strategy reads. `state` is UNCLEAR when the window is too small
    (grade()'s honest "no clean structure" verdict), so consumers can just check it.
    """
    if df is None or len(df) < 1:
        return None
    g = grade(df)
    return {
        "state": g.state,               # IMPULSE/GRIND/CONSOLIDATION/WHIPSAW/UNCLEAR (+dir)
        "direction": g.direction,       # bull | bear | flat
        "strength": g.strength,         # net / range  (the session-bias number)
        "efficiency": g.efficiency,     # |net| / travel (progress axis)
        "acceptance": g.acceptance,     # 1 - va_frac   (fat-POC axis)
        "poc": g.poc,
        "vah": g.vah,                   # breakout level (long)
        "val": g.val,                   # breakout level (short)
    }
