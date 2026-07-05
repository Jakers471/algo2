"""experiments/engine/anchors.py — where to point grade().

Anchors are the containers grade() measures. Two ways to get them (GRADE_SPEC §5):
  - session_anchors : CLOCK-given (the session windows).
  - impulse_anchors : STRUCTURE-detected — roll grade() over the bars and keep the
    contiguous IMPULSE runs. Each run is a sub-anchor (a leg) for the layer below.
And meta_frame() collapses a list of grades into OHLCV meta-candles (for zoom-out).

Reuses the one grade() so the anchor detection can never drift from the measurement.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from src.indicators.sessions import session_instances  # noqa: E402


def session_anchors(df, max_sessions=None):
    """CLOCK-given anchors: one per session. -> [{session, start, end}] (bar indices)."""
    return [{"session": s["session"], "start": int(s["start_pos"]), "end": int(s["end_pos"])}
            for s in session_instances(df, max_sessions)]


def rolling_states(bars, window):
    """grade() over a trailing window at each bar -> per-bar state (None in warm-up)."""
    n = len(bars)
    states = [None] * n
    for i in range(window, n):
        states[i] = grade(bars.iloc[i - window:i + 1]).state
    return states


def impulse_anchors(bars, window=25, gap=12, min_len=8):
    """STRUCTURE-detected anchors: IMPULSE runs, with same-direction bursts separated
    by <= `gap` bars merged (a staggered impulse = impulse -> pause -> impulse is one
    move). Keeps merged spans >= `min_len`. -> [{start, end, state}] (bar indices)."""
    states = rolling_states(bars, window)
    n = len(bars)
    raw = []
    i = window
    while i < n:
        s = states[i]
        if s and s.startswith("IMPULSE"):
            j = i
            while j < n and states[j] == s:
                j += 1
            raw.append([i, j - 1, s])
            i = j
        else:
            i += 1
    merged = []
    for a, b, s in raw:
        if merged and merged[-1][2] == s and a - merged[-1][1] - 1 <= gap:
            merged[-1][1] = b                       # bridge the pause
        else:
            merged.append([a, b, s])
    return [{"start": a, "end": b, "state": s} for a, b, s in merged if b - a + 1 >= min_len]


def meta_frame(grades):
    """Collapse graded anchors to OHLCV meta-candles for the layer above."""
    return pd.DataFrame([g.meta for g in grades], columns=["open", "high", "low", "close", "volume"])
