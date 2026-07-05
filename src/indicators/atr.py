"""src.indicators.atr — Average True Range math (Wilder).

ATR measures volatility as the smoothed *true range* per bar (in price points).
True Range for a bar is the largest of:
  - high - low                      (this bar's range)
  - |high - prev_close|             (gap up from prior close)
  - |low  - prev_close|             (gap down from prior close)
ATR is Wilder's smoothing of TR (an EMA with alpha = 1/period; the recursive
`adjust=False` form), so a period-`n` ATR reacts like an `n`-bar average range.
One value per bar; the first `period - 1` bars have no stable value (the smoother
isn't warmed up yet) and are omitted — same convention as the moving averages.

`period` comes from algo_config.yaml (via src.config) — the single source of truth
for knobs. This module is pure: OHLCV DataFrame in, per-bar ATR values out. The
line's color is a frontend concern (config.atr.color), not computed here. The
same function feeds the chart and (later) the backtester so ATR never drifts.

Returned dict (times are Unix seconds, UTC):
  {
    "period": 14,
    "values": [{"time": <int>, "value": <float>}, ...],
  }
"""
from __future__ import annotations

import pandas as pd

from ..config import atr_config


def _true_range(df: pd.DataFrame) -> pd.Series:
    """Per-bar True Range. The first bar has no prior close, so its TR is just
    high - low."""
    prev_close = df["close"].shift(1)
    hl = df["high"] - df["low"]
    hc = (df["high"] - prev_close).abs()
    lc = (df["low"] - prev_close).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr.iloc[0] = hl.iloc[0]  # no gap component on the first bar
    return tr


def compute_atr(df: pd.DataFrame, period: int | None = None) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> per-bar Wilder ATR values."""
    cfg = atr_config()
    if period is None:
        period = cfg["period"]

    out: dict = {"period": int(period), "values": []}
    if df is None or df.empty or period <= 0:
        return out

    tr = _true_range(df)
    # Wilder smoothing = EMA with alpha = 1/period (recursive form).
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    # Drop the warm-up bars so early, unstable values aren't drawn.
    if period > 1:
        atr.iloc[: period - 1] = float("nan")

    times = df.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)
    out["values"] = [
        {"time": int(t), "value": float(v)}
        for t, v in zip(times, atr.to_numpy())
        if v == v  # drop NaN (smoother not yet warmed up)
    ]
    return out
