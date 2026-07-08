"""src.indicators.ltf_volume_profile — the 1-minute (L2) Volume Profile math.

Draws the SAME profile the strategy's `structure_ltf` reading grades: one volume
profile over the recent 1-minute window (the L2 structure range). It is computed
identically to `grade()`'s internal profile — `n_rows` equal-count rows spanning the
window's high->low, value area at 70% — reusing the project's volume-profile core
(`_profile_for` / `_value_area`), so the drawn POC/VAH/VAL match the monitor's
"1min volume profile" box exactly (one source of truth).

`bars` mirrors snapshot.LTF_BARS (the L2 window); `n_rows` comes from the regime
config (strategy.regime.n_rows), the same knob grade() reads.

Pure: 1-minute OHLCV in, one profile out. Colors are a frontend concern.

Returned dict (prices float; times Unix seconds, UTC):
  {"profile": {
      "start","end","high","low","poc","val","vah",
      "total_volume","max_bin_volume",
      "rows": [{"low","high","mid","volume","poc":bool,"in_va":bool}, ...],
  } | None }
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import strategy_config
from .volume_profile import _profile_for, _value_area

# L2 window (last N 1m bars) — mirrors src.strategy.snapshot.LTF_BARS so the drawn
# profile covers the same range the structure_ltf reading grades.
LTF_BARS = 90
VA_PCT = 0.70          # grade() fixes the value area at 70%; match it here.


def compute_ltf_volume_profile(df: pd.DataFrame, bars: int | None = None,
                               n_rows: int | None = None) -> dict:
    """1-minute OHLCV (tz-aware UTC index) -> one volume profile over the last
    `bars` rows. None if empty/degenerate. `n_rows`/`bars` default to the regime
    config + LTF_BARS so this matches the structure_ltf reading."""
    if df is None or df.empty:
        return {"profile": None}
    if bars is None:
        bars = LTF_BARS
    if n_rows is None:
        n_rows = int(strategy_config()["regime"]["n_rows"])

    w = df.tail(bars)
    highs = w["high"].to_numpy(float)
    lows = w["low"].to_numpy(float)
    vols = w["volume"].to_numpy(float)
    times = w.index.view("int64") // 1_000_000_000

    lo, hi = float(lows.min()), float(highs.max())
    if hi <= lo:
        return {"profile": None}
    rs = (hi - lo) / n_rows
    binvol = _profile_for(highs, lows, vols, range(len(w)), lo, rs, n_rows)
    total = float(binvol.sum())
    if total <= 0:
        return {"profile": None}

    poc_i = int(binvol.argmax())
    val_i, vah_i = _value_area(binvol, poc_i, VA_PCT)
    rows = [{
        "low": lo + i * rs,
        "high": lo + (i + 1) * rs,
        "mid": lo + (i + 0.5) * rs,
        "volume": float(binvol[i]),
        "poc": i == poc_i,
        "in_va": val_i <= i <= vah_i,
    } for i in range(n_rows)]

    return {"profile": {
        "start": int(times[0]), "end": int(times[-1]),
        "high": hi, "low": lo,
        "poc": lo + (poc_i + 0.5) * rs,
        "val": lo + val_i * rs,
        "vah": lo + (vah_i + 1) * rs,
        "total_volume": total,
        "max_bin_volume": float(binvol.max()),
        "rows": rows,
    }}
