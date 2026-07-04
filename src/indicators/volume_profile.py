"""src.indicators.volume_profile — per-session Volume Profile math.

For each session instance (Asia / London / NY per day), build a volume profile
over that session's high->low range:

  1. Slice [low, high] into `bins` equal price rows.
  2. For each bar in the session, distribute its volume across the rows its
     high->low spans, weighted by overlap (the "faithful" method — a bar that
     covers three rows contributes to all three, proportionally). A zero-range
     bar dumps its volume into the single row containing its price.
  3. The per-row totals ARE the histogram.
  4. Landmarks:
       - POC (Point of Control): the row with the most volume.
       - Value Area: expand out from the POC until the collected rows hold
         `value_area_pct` (default 70%) of the session's volume; the block's
         edges are VAL (low) and VAH (high).

Design note: `bins` and `value_area_pct` are PARAMETERS OF THE COMPUTATION, not
display filters. POC and the value area genuinely change with `bins`; VAL/VAH
also change with `value_area_pct` (POC and the histogram do not). The chart and
the strategy call this with the same params so they agree on the numbers.

This module is pure: OHLCV DataFrame in, levels out. It reuses
`sessions.session_instances` so both indicators share one session grouping.

Returned dict (prices are floats; times are Unix seconds, UTC):
  {
    "sessions": ["Asia","London","NY"],
    "bins": <int>, "value_area_pct": <float>,
    "profiles": [{
       "session", "start", "end", "high", "low",
       "poc", "val", "vah", "total_volume", "max_bin_volume",
       "rows": [{"low","high","mid","volume","poc":bool,"in_va":bool}, ...],
    }, ...],
  }
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .sessions import MAX_SESSIONS, session_names, session_instances

DEFAULT_BINS = 24
DEFAULT_VALUE_AREA_PCT = 0.70


def _value_area(vol: np.ndarray, poc_idx: int, pct: float) -> tuple[int, int]:
    """Indices (lo, hi) of the value-area block: expand out from the POC row,
    each step taking the heavier neighbor, until >= pct of total volume."""
    target = vol.sum() * pct
    lo = hi = poc_idx
    acc = float(vol[poc_idx])
    n = len(vol)
    while acc < target and (lo > 0 or hi < n - 1):
        below = vol[lo - 1] if lo > 0 else -1.0
        above = vol[hi + 1] if hi < n - 1 else -1.0
        if above >= below:
            hi += 1
            acc += float(vol[hi])
        else:
            lo -= 1
            acc += float(vol[lo])
    return lo, hi


def _profile_for(highs, lows, vols, positions, low, high, bins):
    """Overlap-weighted volume-per-row for one session -> np.ndarray[bins]."""
    rng = high - low
    row = rng / bins
    binvol = np.zeros(bins)
    for p in positions:
        bl, bh, v = lows[p], highs[p], vols[p]
        if bh <= bl:  # zero-range bar: dump into the row containing its price
            idx = min(max(int((bl - low) / row), 0), bins - 1)
            binvol[idx] += v
            continue
        lo_i = min(max(int((bl - low) / row), 0), bins - 1)
        hi_i = min(max(int((bh - low) / row), 0), bins - 1)
        span = bh - bl
        for bi in range(lo_i, hi_i + 1):
            b_bot = low + bi * row
            b_top = b_bot + row
            overlap = min(bh, b_top) - max(bl, b_bot)
            if overlap > 0:
                binvol[bi] += v * (overlap / span)
    return binvol


def compute_volume_profile(
    df: pd.DataFrame,
    bins: int = DEFAULT_BINS,
    value_area_pct: float = DEFAULT_VALUE_AREA_PCT,
    max_sessions: int = MAX_SESSIONS,
) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> per-session volume profiles."""
    base = {"sessions": session_names(), "bins": bins,
            "value_area_pct": value_area_pct, "profiles": []}
    insts = session_instances(df, max_sessions)
    if not insts:
        return base

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    vols = df["volume"].to_numpy().astype(float)
    times = df.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)

    profiles = []
    for it in insts:
        high, low = it["hi_price"], it["lo_price"]
        if high <= low:  # degenerate (single-bar / flat session)
            continue

        binvol = _profile_for(highs, lows, vols, it["positions"], low, high, bins)
        total = float(binvol.sum())
        if total <= 0:
            continue

        row = (high - low) / bins
        poc_idx = int(binvol.argmax())
        val_idx, vah_idx = _value_area(binvol, poc_idx, value_area_pct)

        rows = [{
            "low": low + i * row,
            "high": low + (i + 1) * row,
            "mid": low + (i + 0.5) * row,
            "volume": float(binvol[i]),
            "poc": i == poc_idx,
            "in_va": val_idx <= i <= vah_idx,
        } for i in range(bins)]

        profiles.append({
            "session": it["session"],
            "start": int(times[it["start_pos"]]),
            "end": int(times[it["end_pos"]]),
            "high": high, "low": low,
            "poc": low + (poc_idx + 0.5) * row,
            "val": low + val_idx * row,
            "vah": low + (vah_idx + 1) * row,
            "total_volume": total,
            "max_bin_volume": float(binvol.max()),
            "rows": rows,
        })

    base["profiles"] = profiles
    return base
