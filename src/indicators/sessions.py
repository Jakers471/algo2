"""src.indicators.sessions — Sessions High/Low math.

For each trading session (Asia / London / NY) on each day, find that session's
high and low, then:
  - a "ray" extends right from the high/low point until a later candle trades
    back to that level (a high is retested when a later high >= it; a low when a
    later low <= it), otherwise to the last bar;
  - "verticals" mark the session's start and end bar times.

Session windows are anchored to America/Chicago (the data's exchange tz),
DST-aware. This module is pure: OHLCV DataFrame in, levels out. Colors are a
frontend concern and deliberately live in the chart renderer, not here.

Returned dict (times are Unix seconds, UTC):
  {
    "sessions":  ["Asia", "London", "NY"],
    "rays":      [{"session","kind":"high"|"low","price","start","end"}, ...],
    "verticals": [{"session","kind":"start"|"end","time"}, ...],
  }
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TZ = "America/Chicago"

# Session windows as minutes-from-midnight in TZ. A window "wraps" past midnight
# when end <= start (e.g. Asia 18:00 -> 03:00). Single source of truth.
SESSIONS = [
    {"name": "Asia",   "start": 18 * 60, "end": 3 * 60},
    {"name": "London", "start": 3 * 60,  "end": 8 * 60},
    {"name": "NY",     "start": 8 * 60,  "end": 17 * 60},
]

# Cap how many recent session instances we return, to bound output on
# timeframes that span many days.
MAX_SESSIONS = 60


def session_names() -> list[str]:
    return [s["name"] for s in SESSIONS]


def _empty() -> dict:
    return {"sessions": session_names(), "rays": [], "verticals": []}


def compute_sessions(df: pd.DataFrame, max_sessions: int = MAX_SESSIONS) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> session H/L rays + verticals."""
    if df is None or df.empty:
        return _empty()

    local = df.index.tz_convert(TZ)
    minute = local.hour.values * 60 + local.minute.values
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    times = df.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)
    n = len(df)

    # Assign each bar to a session (windows here don't overlap -> first match).
    sess = np.full(n, -1, dtype=int)
    for si, s in enumerate(SESSIONS):
        wraps = s["end"] <= s["start"]
        if wraps:
            mask = (minute >= s["start"]) | (minute < s["end"])
        else:
            mask = (minute >= s["start"]) & (minute < s["end"])
        sess[(sess == -1) & mask] = si

    # Instance day: anchor a wrapping session's after-midnight bars to the day it
    # started (i.e. the previous calendar day).
    # Naive datetime64 (local wall-clock), one distinct value per local day.
    anchor = local.normalize().tz_localize(None).to_numpy().copy()
    for si, s in enumerate(SESSIONS):
        if s["end"] <= s["start"]:
            morning = (sess == si) & (minute < s["end"])
            anchor[morning] -= np.timedelta64(1, "D")

    keep = sess >= 0
    if not keep.any():
        return _empty()

    sub = pd.DataFrame({
        "pos": np.arange(n)[keep],
        "sess": sess[keep],
        "anchor": anchor[keep],
        "high": highs[keep],
        "low": lows[keep],
    })

    # One instance per (session, day): find start/end bar and where hi/lo formed.
    insts = []
    for (si, _day), g in sub.groupby(["sess", "anchor"], sort=False):
        hi_i = int(g["high"].values.argmax())
        lo_i = int(g["low"].values.argmin())
        insts.append({
            "sess": int(si),
            "start_pos": int(g["pos"].iloc[0]),
            "end_pos": int(g["pos"].iloc[-1]),
            "hi_price": float(g["high"].iloc[hi_i]),
            "hi_pos": int(g["pos"].iloc[hi_i]),
            "lo_price": float(g["low"].iloc[lo_i]),
            "lo_pos": int(g["pos"].iloc[lo_i]),
        })

    insts.sort(key=lambda x: x["start_pos"])
    insts = insts[-max_sessions:]

    def terminate(pos: int, price: float, up: bool) -> int:
        """Time of the first bar after `pos` that trades to `price`, else last."""
        if pos + 1 >= n:
            return int(times[-1])
        seg = highs[pos + 1:] if up else lows[pos + 1:]
        hit = seg >= price if up else seg <= price
        k = int(np.argmax(hit))
        return int(times[pos + 1 + k]) if hit[k] else int(times[-1])

    rays, verticals = [], []
    for it in insts:
        name = SESSIONS[it["sess"]]["name"]
        rays.append({
            "session": name, "kind": "high", "price": it["hi_price"],
            "start": int(times[it["hi_pos"]]),
            "end": terminate(it["hi_pos"], it["hi_price"], up=True),
        })
        rays.append({
            "session": name, "kind": "low", "price": it["lo_price"],
            "start": int(times[it["lo_pos"]]),
            "end": terminate(it["lo_pos"], it["lo_price"], up=False),
        })
        verticals.append({"session": name, "kind": "start", "time": int(times[it["start_pos"]])})
        verticals.append({"session": name, "kind": "end", "time": int(times[it["end_pos"]])})

    return {"sessions": session_names(), "rays": rays, "verticals": verticals}
