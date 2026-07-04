"""src.indicators — pure indicator math.

Each module takes an OHLCV DataFrame (tz-aware UTC index; columns
open/high/low/close/volume) and returns plain values/levels. No charting, no I/O,
no broker or strategy knowledge — so the same function feeds the live chart, the
backtester, and the strategy identically.
"""
