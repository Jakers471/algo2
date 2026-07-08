"""experiments/engine/legs.py — swing legs: the L2 anchor for grade().

A LEG is a directional swing: price runs, then only reverses once it retraces by a
threshold (`thr`, in price points). This is the structure-detected container the layer
below grade()s — the fractal partner of session_anchors (clock-given) in anchors.py.
Ported from the validated experiments/archive/layer2/session_legs.py `zigzag`.

The threshold is passed in (callers set it = swing_frac * the parent's range) so the SAME
swing_frac carves legs correctly at any scale — the leg definition is scale-invariant.

Pure: highs/lows in, leg spans out. No config, no grade — grade() is applied to each leg
BY THE CALLER (readings/consolidation), so the measurement never drifts from the anchor.
"""
from __future__ import annotations

import numpy as np


def zigzag(h, l, thr: float):
    """Threshold zigzag over highs/lows -> pivots [(idx, price, 'H'|'L')].

    A new pivot forms only once price moves `thr` against the running extreme, so noise
    below `thr` is ignored. Closes with the running extreme (the final, in-progress swing)."""
    h = np.asarray(h, float)
    l = np.asarray(l, float)
    n = len(h)
    piv: list[tuple[int, float, str]] = []
    up = None
    hi_i, lo_i = 0, 0
    for i in range(1, n):
        if h[i] > h[hi_i]:
            hi_i = i
        if l[i] < l[lo_i]:
            lo_i = i
        if up is None:
            if h[hi_i] - l[i] >= thr:
                piv.append((hi_i, float(h[hi_i]), "H")); up = False; lo_i = i
            elif h[i] - l[lo_i] >= thr:
                piv.append((lo_i, float(l[lo_i]), "L")); up = True; hi_i = i
        elif up:                              # looking for a swing high
            if h[hi_i] - l[i] >= thr:
                piv.append((hi_i, float(h[hi_i]), "H")); up = False; lo_i = i
        else:                                 # looking for a swing low
            if h[i] - l[lo_i] >= thr:
                piv.append((lo_i, float(l[lo_i]), "L")); up = True; hi_i = i
    if up:
        piv.append((hi_i, float(h[hi_i]), "H"))
    elif up is False:
        piv.append((lo_i, float(l[lo_i]), "L"))
    return piv


def swing_legs(bars, thr: float):
    """OHLC bars + threshold -> leg spans [(start_pos, end_pos), ...] (integer bar
    positions). Each span is one swing (pivot to pivot); the LAST span is the currently
    forming leg (ends at the running extreme). Empty if fewer than two pivots form."""
    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    piv = zigzag(h, l, thr)
    return [(piv[k - 1][0], piv[k][0]) for k in range(1, len(piv))]
