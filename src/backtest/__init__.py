"""src.backtest — the central backtester (strategy-agnostic).

Drives the SAME pipeline Driver that replay/live use (src.strategy) across history, so
a backtest can't diverge from what you watch bar-by-bar. `runner.run_backtest()` steps
bars per session into a trade log + equity + stats; `report` turns that into a PNG +
printed stats. Swap the strategy in algo_config.yaml — this runs it unchanged.

  python -m src.backtest.report --start 2024-12-01 --sessions 10
"""
from .runner import run_backtest  # noqa: F401

