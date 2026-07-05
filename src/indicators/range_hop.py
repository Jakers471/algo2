"""src.indicators.range_hop — TEMP/EXPERIMENTAL connected session high/low + bias.

Two things, both session-anchored:

1. LINES — each session's HIGH and LOW as CONNECTED stepped lines across sessions,
   colored by direction: GREEN when the level rose (higher high / higher low), RED
   when it fell. Develops within a session, restarts the next.

2. BIAS — directional regime from breaking the PREVIOUS session's range: while a bar
   CLOSES above the prior session's high the regime is BULLISH, a close below its low
   flips it BEARISH; holds until flipped. Rendered as a full-height green/red tint.

Pure: OHLCV DataFrame in, segments + regime out. Reuses session_instances. TEMP.

Returned dict (prices float; times Unix seconds UTC):
  {
    "segments": [{"session","high","low","start","end","active","high_dir","low_dir"}...],
    "regime":   [{"start","end","bias"}, ...],   # bias: "bull" | "bear"
  }
"""
from __future__ import annotations

from .sessions import session_instances


def compute_range_hop(df, max_sessions=None) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> H/L segments + bias regime."""
    insts = session_instances(df, max_sessions)
    if not insts:
        return {"segments": [], "regime": []}

    times = df.index.view("int64") // 1_000_000_000  # Unix seconds
    closes = df["close"].to_numpy()
    last_t = int(times[-1])
    n = len(insts)

    segments = []
    prev_hi = prev_lo = None
    for i, s in enumerate(insts):
        hi, lo = float(s["hi_price"]), float(s["lo_price"])
        start_t = int(times[s["start_pos"]])
        end_t = int(times[insts[i + 1]["start_pos"]]) if i + 1 < n else last_t
        segments.append({
            "session": s["session"], "high": hi, "low": lo,
            "start": start_t, "end": end_t, "active": i == n - 1,
            "high_dir": None if prev_hi is None else ("up" if hi >= prev_hi else "down"),
            "low_dir": None if prev_lo is None else ("up" if lo >= prev_lo else "down"),
        })
        prev_hi, prev_lo = hi, lo

    # --- bias regime: break (close) of the PREVIOUS session's range ---
    regime = []
    bias = None
    span_start = None
    ref_hi = ref_lo = None
    for s in insts:
        for p in s["positions"]:
            if ref_hi is not None:
                c = float(closes[p])
                new = bias
                if c > ref_hi:
                    new = "bull"
                elif c < ref_lo:
                    new = "bear"
                if new != bias:
                    if bias is not None:
                        regime.append({"start": span_start, "end": int(times[p]), "bias": bias})
                    bias = new
                    span_start = int(times[p])
        ref_hi, ref_lo = float(s["hi_price"]), float(s["lo_price"])
    if bias is not None:
        regime.append({"start": span_start, "end": last_t, "bias": bias})

    return {"segments": segments, "regime": regime}
