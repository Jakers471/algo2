"""src.indicators.moving_average — Moving Average math (SMA + EMA).

For each configured line (EMA 20 / 50 / 200 by default), compute a moving average
of a chosen price `source` (close by default) over the bars:
  - sma: simple rolling mean over `period` bars.
  - ema: exponential moving average, span=`period`, recursive (adjust=False) —
    weights recent bars more, so it tracks price closer than an SMA.
One value per bar; the first `period - 1` bars of each line have no value (the
window isn't full yet) and are omitted.

Types, periods, colors, and the price source all come from algo_config.yaml (via
src.config) — the single source of truth for knobs. This module is pure: OHLCV
DataFrame in, per-bar line values out. Colors are a frontend concern.

Returned dict (times are Unix seconds, UTC):
  {
    "source": "close",
    "lines": [
      {"type": "ema", "period": 20,
       "values": [{"time": <int>, "value": <float>}, ...]},
      ...
    ],
  }
"""
from __future__ import annotations

import pandas as pd

from ..config import moving_averages_config


def _source_series(df: pd.DataFrame, source: str) -> pd.Series:
    """Resolve the price field to average. Supports the raw OHLC columns plus the
    common composites hl2 / hlc3 / ohlc4; unknown names fall back to close."""
    if source == "hl2":
        return (df["high"] + df["low"]) / 2.0
    if source == "hlc3":
        return (df["high"] + df["low"] + df["close"]) / 3.0
    if source == "ohlc4":
        return (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    if source in ("open", "high", "low", "close"):
        return df[source]
    return df["close"]


def _moving_average(price: pd.Series, period: int, kind: str) -> pd.Series:
    """One MA series. `kind` is 'ema' (recursive, span=period) or 'sma' (rolling
    mean). Both emit NaN until the first `period` bars are available."""
    if kind == "ema":
        return price.ewm(span=period, adjust=False, min_periods=period).mean()
    return price.rolling(window=period, min_periods=period).mean()


def compute_moving_averages(df: pd.DataFrame, source: str | None = None) -> dict:
    """OHLCV DataFrame (tz-aware UTC index) -> per-bar MA lines (one per config line)."""
    cfg = moving_averages_config()
    if source is None:
        source = cfg["source"]

    out = {"source": source, "lines": []}
    if df is None or df.empty or not cfg["lines"]:
        return out

    price = _source_series(df, source)
    times = df.index.view("int64") // 1_000_000_000  # Unix seconds (UTC)

    for ln in cfg["lines"]:
        period, kind = ln["period"], ln["type"]
        if period <= 0:
            continue
        ma = _moving_average(price, period, kind)
        values = [
            {"time": int(t), "value": float(v)}
            for t, v in zip(times, ma.to_numpy())
            if v == v  # drop NaN (window not yet full)
        ]
        out["lines"].append({"type": kind, "period": period, "values": values})

    return out
