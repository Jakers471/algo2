"""src.strategy.readings.consolidation — the tradeable L2 base (a fact).

The VA-breakout strategy enters on the break of a 1m CONSOLIDATION's value area. The
CONSOLIDATION itself — where it is, its VAH/VAL — is an objective FACT (found by the
frozen engine), so it lives here as a reading. Whether to TRADE its break is the
decider's opinion, not this module's.

Detection mirrors experiments/engine/research/backtest_equity.py `collect()`:
  roll grade() over recent 1m bars -> per-bar state -> keep the most recent
  CONSOLIDATION run >= MIN_LEN bars -> grade it for VAH/VAL. None if there isn't one
  recently (or it is stale). Same computes as every other scale — fractal.

TODO (config): MIN_LEN / STATE_WINDOW / MAX_AGE are strategy knobs; move to
algo_config.yaml (convention #3) once the shape settles.
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_REPO, "experiments", "engine"))
from grade import grade  # noqa: E402

DET_WINDOW = 120     # recent 1m bars to scan
STATE_WINDOW = 25    # rolling_states window (matches the backtest)
MIN_LEN = 15         # min CONSOLIDATION length in bars (matches the backtest)
MAX_AGE = 40         # ignore a base that ended > this many bars ago (gone stale)

# PERF: a 1m bar's state = grade(its trailing 25-bar window).state — deterministic for a
# fixed dataset, so we compute it ONCE and reuse it across every bar-step (instead of
# re-grading the whole window each bar, the ~50x redundancy). Keyed by (window, bar-ts).
# Bounded by clear_state_cache() (the runner clears per session; the server on rebuild).
_STATE_CACHE: dict = {}


def clear_state_cache() -> None:
    _STATE_CACHE.clear()


def _states_cached(win, window):
    """Same result as rolling_states(win, window), but each bar's state is memoized by
    timestamp so a sequence of overlapping windows only pays for the NEW bars."""
    idx = win.index
    states = [None] * len(win)
    for i in range(window, len(win)):
        key = (window, idx[i].value)
        s = _STATE_CACHE.get(key)
        if s is None:
            s = grade(win.iloc[i - window:i + 1]).state
            _STATE_CACHE[key] = s
        states[i] = s
    return states


def _cons_runs(states, min_len):
    out, i = [], 0
    while i < len(states):
        j = i
        while j < len(states) and states[j] == states[i]:
            j += 1
        if states[i] == "CONSOLIDATION" and j - i >= min_len:
            out.append((i, j - 1))
        i = j
    return out


def read_consolidation(ltf_df) -> dict | None:
    """Recent 1m bars -> the most recent tradeable CONSOLIDATION base, or None.

    `{vah, val, poc, len, ended_ago}` — the value-area edges are the breakout levels;
    `ended_ago` = bars since the base completed (0 = still forming on the last bar)."""
    if ltf_df is None or len(ltf_df) < STATE_WINDOW + MIN_LEN:
        return None
    win = ltf_df.tail(DET_WINDOW)
    states = _states_cached(win, STATE_WINDOW)
    runs = _cons_runs(states, MIN_LEN)
    if not runs:
        return None
    a, b = runs[-1]
    ended_ago = len(win) - 1 - b
    if ended_ago > MAX_AGE:
        return None
    g = grade(win.iloc[a:b + 1])
    if g.vah <= g.val:
        return None
    return {"vah": g.vah, "val": g.val, "poc": g.poc, "len": b - a + 1, "ended_ago": ended_ago}
