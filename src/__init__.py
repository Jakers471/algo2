"""src — the algorithmic trading backend (the "brain").

Indicator math, strategy/decision logic, broker abstraction, and the backtest
engine live here. This is the single source of truth for anything numeric: the
chart and the backtester both consume the same computations so they can't drift.

Layout:
  src/indicators/  — pure indicator math (OHLCV in, values out; no UI)
  src/strategy/    — decision logic (entries/exits) built on indicators
  src/brokers/     — broker abstraction layer + per-broker adapters
  src/backtest/    — backtest engine + metrics
"""
