"""src.strategy.readings.session_structure — the session's structural H/L (facts).

Reads the current session's raw and swing structural high/low so the Snapshot (and
the replay monitor that consumes it) carries them. Facts only — whether a break of
these levels means anything is the score/decide stages' job.

  RAW    the session's absolute high/low (extreme wicks).
  SWING  the last CONFIRMED swing-high/low (BOS-style) from the threshold zigzag —
         the levels whose break signals a break of structure.

The math is the single source of truth in src/indicators/session_structure.py, so
the chart overlay and this reading show the identical numbers. `swing_frac` is the
shared swing threshold (strategy.consolidation.swing_frac), passed in by build_snapshot.
"""
from __future__ import annotations

from ...indicators.session_structure import structure_of


def read_session_structure(sess_bars, swing_frac: float | None = None) -> dict | None:
    """Current session's bars -> {high, high_time, low, low_time, swing_high,
    swing_high_time, swing_low, swing_low_time}, or None if empty.

    Drops the raw `pivots` list (drawing-only; the chart overlay computes its own)
    so the Snapshot stays lean — the strategy reads levels, not the whole zigzag."""
    s = structure_of(sess_bars, swing_frac)
    if s is None:
        return None
    return {k: v for k, v in s.items() if k != "pivots"}
