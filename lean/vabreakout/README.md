# vabreakout — VA-breakout on QuantConnect LEAN

A **parallel, isolated** port of the `src/strategy` VA-breakout to LEAN, so you can validate
and sweep at LEAN speed (and it's the same engine you'd trade live on). **Nothing in the main
project depends on this folder, and this folder doesn't import the main project** — the math is
copied into `grade_lib.py` so it's fully self-contained.

## Files
- `main.py` — the `QCAlgorithm`: continuous NQ, minute base + 5m consolidator, Chicago timezone,
  session-bias (L1) + 1m consolidation (L2) → break entry, intrabar (1m) exits.
- `grade_lib.py` — the strategy's brain, flattened from `src/indicators/volume_profile.py`,
  `experiments/engine/grade.py`, and `src/strategy/{readings,decide}` with all config inlined.

## Mapping to the pipeline (same shape)
| src/strategy | here |
|---|---|
| `structure` reading (L1 5m session) | `grade(session 5m bars).strength` |
| `consolidation` reading (L2 1m) | `read_consolidation(recent 1m bars)` |
| `decide/va_breakout` | `decide(strength, cons, price)` |
| `manage/fixed` + book | entry via `market_order`, 1m intrabar stop/target, one-trade-per-base |

## Run it
You have the LEAN CLI + a QC subscription. From the repo root (or wherever your `lean` data dir is):

```bash
# local (Docker) — fast, uses your QC data subscription:
lean backtest lean/vabreakout

# or in the cloud (their servers, downloadable results):
lean cloud backtest "vabreakout" --push --open
```
Edit the dates in `main.py` `initialize()` to set the range. Data is available from **May 2009**.

> **v1 caveat:** written from the LEAN Python examples but not run in this environment (no
> Docker/QC auth here). The first `lean backtest` may surface an API mismatch (symbol/consolidator/
> order call) — paste the error and we fix it fast.

## Getting results back into the main project
LEAN writes each run to `lean/vabreakout/backtests/<timestamp>/` (local) or downloadable from cloud:
- **Statistics + equity + orders** — in the result JSON (automatic).
- Once we see that JSON from your first run, we add `import_results.py` here that pairs the fills
  into round-trip trades and writes a `trades.parquet` in the SAME schema as `src/backtest`, so
  `src/backtest/report.py` and the research scripts analyze LEAN runs unchanged.

## Honest caveat on the numbers
QC's continuous-contract futures data (with rollover) differs from the raw front-month parquets the
local backtest uses, so the **edge should reproduce, not the exact trade list.** For apples-to-apples,
LEAN CLI can ingest your own parquets as a custom data source (more setup — skip at first).
