"""lean/vabreakout/grade_lib.py — the strategy's math, self-contained for LEAN.

A flattened COPY of the project's brain (src/indicators/volume_profile.py `_profile_for`
/`_value_area`, experiments/engine/grade.py `grade`, and the readings/decide logic), with
all config values inlined so it has ZERO dependency on src/, algo_config.yaml, or the chart.
Pure numpy/pandas — drops straight into a QuantConnect Python algorithm.

Keep this in sync with the source of truth if the frozen engine ever changes (it shouldn't).
The QuantConnect data differs from the local parquets (continuous contract w/ rollover), so
expect the EDGE to reproduce, not the exact trade list.
"""
from collections import namedtuple

import numpy as np

# --- grade() constants (experiments/engine/grade.py) ---
N_ROWS = 24
E_CUT = 0.38
A_CUT = 0.55
MIN_BARS = 8
# --- detection + decision constants (readings/consolidation.py, decide/va_breakout.py) ---
STATE_WINDOW = 25
MIN_LEN = 15
MAX_AGE = 40
DET_WINDOW = 120
BIAS_STR = 0.3
TARGET_R = 2.0

Grade = namedtuple("Grade", "direction net rng strength efficiency acceptance poc vah val state")


def _value_area(vol, poc_idx, pct):
    target = vol.sum() * pct
    lo = hi = poc_idx
    acc = float(vol[poc_idx])
    n = len(vol)
    while acc < target and (lo > 0 or hi < n - 1):
        below = vol[lo - 1] if lo > 0 else -1.0
        above = vol[hi + 1] if hi < n - 1 else -1.0
        if above >= below:
            hi += 1; acc += float(vol[hi])
        else:
            lo -= 1; acc += float(vol[lo])
    return lo, hi


def _profile_for(highs, lows, vols, positions, base, row_size, n_rows):
    binvol = np.zeros(n_rows)
    for p in positions:
        bl, bh, v = lows[p], highs[p], vols[p]
        if bh <= bl:
            idx = min(max(int((bl - base) / row_size), 0), n_rows - 1)
            binvol[idx] += v
            continue
        lo_i = min(max(int((bl - base) / row_size), 0), n_rows - 1)
        hi_i = min(max(int((bh - base) / row_size), 0), n_rows - 1)
        span = bh - bl
        for bi in range(lo_i, hi_i + 1):
            b_bot = base + bi * row_size
            overlap = min(bh, b_bot + row_size) - max(bl, b_bot)
            if overlap > 0:
                binvol[bi] += v * (overlap / span)
    return binvol


def _profile(highs, lows, vols, n_rows=N_ROWS):
    lo, hi = float(lows.min()), float(highs.max())
    rng = (hi - lo) or 1e-9
    rs = rng / n_rows
    binvol = _profile_for(highs, lows, vols, range(len(highs)), lo, rs, n_rows)
    if binvol.sum() <= 0:
        return lo, rs, 0, 0, n_rows - 1
    poc = int(binvol.argmax())
    va_lo, va_hi = _value_area(binvol, poc, 0.70)
    return lo, rs, poc, va_lo, va_hi


def grade(o, h, l, c, v):
    """OHLCV numpy arrays (one anchor) -> Grade. Mirrors experiments/engine/grade.py."""
    n = len(c)
    O, C, H, L = float(o[0]), float(c[-1]), float(h.max()), float(l.min())
    rng = (H - L) or 1e-9
    net = C - O
    diffs = np.diff(c)
    travel = float(np.abs(diffs).sum()) or 1e-9
    base, rs, poc_i, va_lo, va_hi = _profile(h, l, v)
    poc = base + (poc_i + 0.5) * rs
    vah = base + (va_hi + 1) * rs
    val = base + va_lo * rs
    acceptance = 1 - (va_hi - va_lo + 1) / N_ROWS
    direction = "bull" if net > 0 else "bear" if net < 0 else "flat"
    efficiency = abs(net) / travel
    if n < MIN_BARS:
        state = "UNCLEAR"
    else:
        d = "UP" if direction == "bull" else "DN"
        if efficiency >= E_CUT:
            state = ("GRIND " if acceptance >= A_CUT else "IMPULSE ") + d
        else:
            state = "CONSOLIDATION" if acceptance >= A_CUT else "WHIPSAW"
    return Grade(direction, net, rng, net / rng, efficiency, acceptance, poc, vah, val, state)


def _rolling_states(o, h, l, c, v, window):
    n = len(c)
    states = [None] * n
    for i in range(window, n):
        s = slice(i - window, i + 1)
        states[i] = grade(o[s], h[s], l[s], c[s], v[s]).state
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


def state_of(o, h, l, c, v):
    """State of ONE trailing window (the last STATE_WINDOW bars). main.py calls this once
    per new 1m bar and keeps the states — so we never re-grade the whole window each 5m bar
    (the perf fix: O(1)/bar instead of O(window)/bar)."""
    return grade(o, h, l, c, v).state


def find_consolidation(states, o, h, l, c, v):
    """PRECOMPUTED per-1m-bar states + aligned OHLCV -> the current CONSOLIDATION base
    {vah,val,poc,len,ago} or None. No re-grading of the rolling window — that already
    happened once per bar via state_of()."""
    n = len(states)
    if n < STATE_WINDOW + MIN_LEN:
        return None
    lo = max(0, n - DET_WINDOW)
    st = list(states[lo:])
    for i in range(min(STATE_WINDOW, len(st))):   # replicate the tail-window warm-up (None)
        st[i] = None
    runs = _cons_runs(st, MIN_LEN)
    if not runs:
        return None
    a, b = runs[-1]
    ended_ago = (n - lo) - 1 - b
    if ended_ago > MAX_AGE:
        return None
    A, B = lo + a, lo + b                      # absolute indices into the bar arrays
    g = grade(o[A:B + 1], h[A:B + 1], l[A:B + 1], c[A:B + 1], v[A:B + 1])
    if g.vah <= g.val:
        return None
    return {"vah": g.vah, "val": g.val, "poc": g.poc, "len": B - A + 1, "ended_ago": ended_ago}


def decide(strength, cons, price):
    """L1 bias strength + L2 base + current price -> intent {dir,entry,stop,target} or None.
    Mirrors decide/va_breakout.py."""
    if strength is None or not cons:
        return None
    vah, val = cons["vah"], cons["val"]
    if vah <= val:
        return None
    risk = vah - val
    if strength >= BIAS_STR and price > vah:
        return {"direction": "long", "entry": vah, "stop": val, "target": vah + TARGET_R * risk}
    if strength <= -BIAS_STR and price < val:
        return {"direction": "short", "entry": val, "stop": vah, "target": val - TARGET_R * risk}
    return None
