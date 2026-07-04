"""src.indicators.volume_profile — per-session Volume Profile math.

For each session instance (Asia / London / NY per day), build a volume profile
over that session's high->low range:

  1. Slice price into equal rows of fixed height `row_size`, anchored to an
     ABSOLUTE price grid (row edges at multiples of row_size). Because the grid
     is shared, every row is the same height and rows line up across sessions.
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

Design note: `row_size` and `value_area_pct` are PARAMETERS OF THE COMPUTATION
(from algo_config.yaml), not display filters. POC and the value area genuinely
change with `row_size`; VAL/VAH also change with `value_area_pct` (POC and the
histogram do not). The chart and the strategy call this with the same params.

Pure: OHLCV DataFrame in, levels out. Reuses `sessions.session_instances` so both
indicators share one session grouping.

Returned dict (prices are floats; times are Unix seconds, UTC):
  {
    "sessions": ["Asia","London","NY"],
    "row_size": <float>, "value_area_pct": <float>,
    "profiles": [{
       "session", "start", "end", "high", "low",
       "poc", "val", "vah", "total_volume", "max_bin_volume",
       "rows": [{"low","high","mid","volume","poc":bool,"in_va":bool}, ...],
    }, ...],
  }
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..config import volume_profile_config
from .sessions import session_names, session_instances


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


def _profile_for(highs, lows, vols, positions, base, row_size, n_rows):
    """Overlap-weighted volume-per-row for one session, on a grid whose row i
    spans [base + i*row_size, base + (i+1)*row_size). -> np.ndarray[n_rows]."""
    binvol = np.zeros(n_rows)
    for p in positions:
        bl, bh, v = lows[p], highs[p], vols[p]
        if bh <= bl:  # zero-range bar: dump into the row containing its price
            idx = min(max(int((bl - base) / row_size), 0), n_rows - 1)
            binvol[idx] += v
            continue
        lo_i = min(max(int((bl - base) / row_size), 0), n_rows - 1)
        hi_i = min(max(int((bh - base) / row_size), 0), n_rows - 1)
        span = bh - bl
        for bi in range(lo_i, hi_i + 1):
            b_bot = base + bi * row_size
            b_top = b_bot + row_size
            overlap = min(bh, b_top) - max(bl, b_bot)
            if overlap > 0:
                binvol[bi] += v * (overlap / span)
    return binvol


def compute_volume_profile(
    df: pd.DataFrame,
    row_size: float | None = None,
    value_area_pct: float | None = None,
    max_sessions: int | None = None,
) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> per-session volume profiles."""
    vpcfg = volume_profile_config()
    if row_size is None:
        row_size = vpcfg["row_size"]
    if value_area_pct is None:
        value_area_pct = vpcfg["value_area_pct"]
    row_size = float(row_size)

    base_out = {"sessions": session_names(), "row_size": row_size,
                "value_area_pct": value_area_pct, "profiles": []}
    insts = session_instances(df, max_sessions)
    if not insts or row_size <= 0:
        return base_out

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    vols = df["volume"].to_numpy().astype(float)
    times = df.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)

    profiles = []
    for it in insts:
        high, low = it["hi_price"], it["lo_price"]
        if high <= low:  # degenerate (single-bar / flat session)
            continue

        # Absolute grid: snap the low down / high up to row_size multiples so
        # rows are shared across sessions.
        base = math.floor(low / row_size) * row_size
        top = math.ceil(high / row_size) * row_size
        n_rows = max(1, int(round((top - base) / row_size)))

        binvol = _profile_for(highs, lows, vols, it["positions"], base, row_size, n_rows)
        total = float(binvol.sum())
        if total <= 0:
            continue

        poc_idx = int(binvol.argmax())
        val_idx, vah_idx = _value_area(binvol, poc_idx, value_area_pct)

        rows = [{
            "low": base + i * row_size,
            "high": base + (i + 1) * row_size,
            "mid": base + (i + 0.5) * row_size,
            "volume": float(binvol[i]),
            "poc": i == poc_idx,
            "in_va": val_idx <= i <= vah_idx,
        } for i in range(n_rows)]

        profiles.append({
            "session": it["session"],
            "start": int(times[it["start_pos"]]),
            "end": int(times[it["end_pos"]]),
            "high": high, "low": low,
            "poc": base + (poc_idx + 0.5) * row_size,
            "val": base + val_idx * row_size,
            "vah": base + (vah_idx + 1) * row_size,
            "total_volume": total,
            "max_bin_volume": float(binvol.max()),
            "rows": rows,
        })

    base_out["profiles"] = profiles
    return base_out
