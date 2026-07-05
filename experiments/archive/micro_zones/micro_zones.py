"""src.indicators.micro_zones — TEMP/EXPERIMENTAL micro-consolidation finder.

Single-timeframe and self-contained (one profile PER timeframe):
  1. BASE  — the session volume profile computed on THIS timeframe's own bars.
     Its VAH/VAL (read, not detected) are the base consolidation's price channel.
  2. MICRO — on the SAME timeframe, inside that VAH-VAL channel, find tight-range
     runs of `min_bars`..`max_bars` bars. Each is a micro-consolidation zone,
     bounded in time (the run) and price (its tight sub-band).

Nothing here mixes timeframes: point it at 1min and base+micros are both 1min;
point it at 5min and they're both 5min. Bar-count width (30..80) is scale-relative,
so it means ~30-80 min on 1min, ~2.5-6.7h on 5min.

One tightness dial: a run stays "consolidating" while its band <= `tightness` of
the channel height (VAH-VAL), so it auto-scales per session. Runs must sit inside
the channel — consolidations live in the value area, breakouts in the tails.

Pure: one OHLCV frame (tz-aware UTC) in, boxes out. Reuses compute_volume_profile
for the VAH/VAL channel. TEMP — knobs are function defaults (URL-overridable),
nothing in algo_config.yaml yet.

Returned dict (prices float; times Unix seconds UTC):
  {
    "profiles": [{
       "session","start","end","vah","val",
       "zones": [{"start","end","lo","hi"}, ...],
    }, ...],
  }
"""
from __future__ import annotations

import numpy as np

from .volume_profile import compute_volume_profile


def _tight_runs(pos, highs, lows, val, vah, cap, min_bars, max_bars):
    """Maximal runs of bars (indices in `pos`) that stay inside [val,vah] and
    whose aggregate band <= cap. Keep only runs `min_bars`..`max_bars` wide.
    -> list of (start_pos, end_pos, run_lo, run_hi)."""
    zones = []
    N = len(pos)
    start = 0
    while start < N:
        p0 = pos[start]
        if not (val <= lows[p0] and highs[p0] <= vah):
            start += 1
            continue
        run_lo, run_hi, end = lows[p0], highs[p0], start
        j = start + 1
        while j < N:
            p = pos[j]
            nlo, nhi = min(run_lo, lows[p]), max(run_hi, highs[p])
            if nlo < val or nhi > vah or (nhi - nlo) > cap:
                break
            run_lo, run_hi, end = nlo, nhi, j
            j += 1
        width = end - start + 1
        if min_bars <= width <= max_bars:
            zones.append((pos[start], pos[end], float(run_lo), float(run_hi)))
            start = end + 1
        elif width > max_bars:   # bigger than a micro — step past it
            start = end + 1
        else:                    # too short — advance one and retry
            start += 1
    return zones


def compute_micro_zones(
    df,
    tightness: float = 0.40,   # micro band must stay <= tightness * (VAH-VAL)
    min_bars: int = 30,        # min consolidation width, in THIS tf's bars
    max_bars: int = 80,        # max consolidation width, in THIS tf's bars
) -> dict:
    """One OHLCV frame -> per-session VAH/VAL channel + micro zones, all on that
    frame's own timeframe."""
    base = compute_volume_profile(df)   # reads row_size/value_area_pct from config
    out = {"profiles": []}
    if not base["profiles"] or df is None or df.empty:
        return out

    t = df.index.view("int64") // 1_000_000_000  # Unix seconds
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()

    for prof in base["profiles"]:
        val, vah = prof["val"], prof["vah"]
        channel = vah - val
        if channel <= 0:
            continue
        # this session's bars on this timeframe
        mask = (t >= prof["start"]) & (t <= prof["end"])
        pos = np.nonzero(mask)[0]
        zones = []
        if len(pos) >= min_bars:
            cap = tightness * channel
            for (sp, ep, lo, hi) in _tight_runs(pos, h, l, val, vah, cap,
                                                min_bars, max_bars):
                zones.append({"start": int(t[sp]), "end": int(t[ep]),
                              "lo": lo, "hi": hi})
        out["profiles"].append({
            "session": prof["session"],
            "start": prof["start"], "end": prof["end"],
            "vah": vah, "val": val,
            "zones": zones,
        })
    return out
