"""src.indicators.volume — per-bar Volume (time-based) math.

The plain volume histogram: one value per bar, the traded volume for that bar.
Each bar also carries a direction flag (`up` = close >= open) so the frontend can
tint rising vs. falling bars — colors are a presentation concern and live in the
renderer/config, not here.

This is the deliberately-trivial counterpart to volume_profile: that one buckets
volume by PRICE (a sideways, per-session profile); this one keeps volume by TIME
(a vertical bar under each candle). Same source of truth, though — the chart and
the backtester both call this so a "volume" value never drifts between them.

Pure: OHLCV DataFrame in, per-bar values out. No UI, no I/O, no config knobs
(volume has none — there is nothing to parametrize about "the bar's volume").

Returned dict (times are Unix seconds, UTC):
  {
    "bars": [{"time": <int>, "value": <float>, "up": <bool>}, ...],
  }
"""
from __future__ import annotations

import pandas as pd


def compute_volume(df: pd.DataFrame) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> per-bar volume values."""
    out: dict = {"bars": []}
    if df is None or df.empty:
        return out

    times = df.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    vols = df["volume"].to_numpy().astype(float)

    out["bars"] = [
        {"time": int(t), "value": float(v), "up": bool(c >= o)}
        for t, v, o, c in zip(times, vols, opens, closes)
    ]
    return out
