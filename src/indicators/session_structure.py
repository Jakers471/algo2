"""src.indicators.session_structure — Session structural High/Low math.

For each trading session (Asia / London / NY) this derives TWO kinds of high/low:

  - RAW    the session's absolute max-high and min-low (the extreme wicks), and
  - SWING  the last CONFIRMED swing-high and swing-low pivots (BOS-style market
           structure): the levels whose break signals a break of structure. Swings
           come from the threshold zigzag (experiments/engine/legs.zigzag) with
           `thr = swing_frac * session range` — the SAME scale-invariant swing
           definition the L2 base detector uses (strategy.consolidation.swing_frac),
           so "a swing" means the same reversal magnitude everywhere.

This is the single source of truth: the chart renderer
(chart/static/js/indicators/session_structure.js) fetches it, and the strategy
reading (src/strategy/readings/session_structure.py) calls `structure_of()` on the
current session so the Snapshot carries the identical numbers.

Pure: OHLCV DataFrame in, levels out. No UI, no I/O. Colors are a frontend concern.

`structure_of()` returns (times are Unix seconds, UTC; a swing is None when no
reversal of `thr` has confirmed yet):
  {
    "high", "high_time",  "low", "low_time",              # raw extremes
    "swing_high", "swing_high_time",                      # last confirmed swing H
    "swing_low",  "swing_low_time",                       # last confirmed swing L
    "pivots": [{"time","price","kind":"H"|"L"}, ...],     # confirmed pivots (drawing)
  }
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

from ..config import strategy_config
from .sessions import session_instances, session_names

# legs.zigzag is the validated swing detector (see readings/consolidation for the
# same import). It still lives under experiments/engine while it is the frozen core.
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "experiments", "engine"))
from legs import zigzag  # noqa: E402


def _default_swing_frac() -> float:
    """The shared swing threshold (strategy.consolidation.swing_frac) — reused so a
    'swing' is the same reversal magnitude at the session scale as at the L2 scale."""
    return float(strategy_config()["consolidation"]["swing_frac"])


def structure_of(bars: pd.DataFrame, swing_frac: float | None = None) -> dict | None:
    """One session's bars -> its raw + swing structural high/low. None if empty.

    `swing_frac` (fraction of the session's range) sets the zigzag reversal
    threshold; None resolves it from config (strategy.consolidation.swing_frac)."""
    if bars is None or len(bars) == 0:
        return None
    if swing_frac is None:
        swing_frac = _default_swing_frac()

    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    times = bars.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)

    hi_i = int(h.argmax())
    lo_i = int(l.argmin())
    out = {
        "high": float(h[hi_i]), "high_time": int(times[hi_i]),
        "low": float(l[lo_i]), "low_time": int(times[lo_i]),
        "swing_high": None, "swing_high_time": None,
        "swing_low": None, "swing_low_time": None,
        "pivots": [],
    }

    rng = float(h[hi_i] - l[lo_i])
    if rng <= 0:
        return out

    piv = zigzag(h, l, swing_frac * rng)
    # zigzag closes with the running (still-forming) extreme as its LAST pivot; that
    # one isn't confirmed by a reversal yet, so BOS structure uses only piv[:-1].
    confirmed = piv[:-1]
    out["pivots"] = [
        {"time": int(times[i]), "price": float(p), "kind": k} for i, p, k in confirmed
    ]
    for i, p, k in reversed(confirmed):
        if k == "H" and out["swing_high"] is None:
            out["swing_high"], out["swing_high_time"] = float(p), int(times[i])
        elif k == "L" and out["swing_low"] is None:
            out["swing_low"], out["swing_low_time"] = float(p), int(times[i])
        if out["swing_high"] is not None and out["swing_low"] is not None:
            break
    return out


def compute_session_structure(df: pd.DataFrame, max_sessions: int | None = None,
                              swing_frac: float | None = None) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> per-session structural H/L.

    Groups bars into session instances (the SAME grouping the Sessions H/L and
    Volume-Profile indicators use) and reads `structure_of()` on each. Returns:
      {"sessions": [...names...],
       "structures": [{session, start, end, high, low, swing_high, swing_low, ...}, ...]}
    """
    if swing_frac is None:
        swing_frac = _default_swing_frac()
    insts = session_instances(df, max_sessions)
    if not insts:
        return {"sessions": session_names(), "structures": []}

    times = df.index.view("int64") // 1_000_000_000
    structures = []
    for it in insts:
        bars = df.iloc[it["start_pos"]:it["end_pos"] + 1]
        s = structure_of(bars, swing_frac)
        if s is None:
            continue
        s["session"] = it["session"]
        s["start"] = int(times[it["start_pos"]])
        s["end"] = int(times[it["end_pos"]])
        structures.append(s)
    return {"sessions": session_names(), "structures": structures}
