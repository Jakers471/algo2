# Pipeline validation — 2024 (phase 5, GRADUATION COMPLETE)

The `src/strategy` + `src/backtest` pipeline (the SAME code that runs replay/live) backtested
over **2024-01-01 → 2025-01-10**, net of costs ($4 commission + 1 tick/side slippage). This is
the proof the strategy graduated from research scripts into the production pipeline WITHOUT
changing the edge.

## Result
- **271 trades · 55% win · +0.49R expectancy · +133R total · −12.5R max drawdown** (net of costs)
- Matches/beats the research engine (`experiments/engine/research/backtest_equity.py`: +0.45R gross).

## Files (a permanent copy; the live `../pipeline_run/` is gitignored scratch)
- `equity.png` — the cumulative-R curve.
- `bars.parquet` — **everything the pipeline saw+did**, one row per 5m bar (69,901 rows × 35 cols):
  price/high/low, L1 + L2 structure, consolidation levels, volume/profile, intent, action, book.
- `trades.parquet` — the 271 closed trades (dir/entry/exit/R/reason/session/cost_R/R_net).
- `stats.json`, `meta.json` — summary + run parameters.

## Regenerate
```bash
python -m src.backtest.report --start 2024-01-01 --save experiments/engine/out/pipeline_run
```
Load for analysis: `pandas.read_parquet("bars.parquet")` / `read_parquet("trades.parquet")`.
