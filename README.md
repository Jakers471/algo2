# volume_profile_algo

A fractal **volume-profile "VA-breakout"** day-trading system for NQ futures, plus the
research + charting tooling around it. One measurement engine grades price structure at
any timescale; the strategy trades value-area breakouts off it.

> **New here (human or AI)? Read the "Start here" path below in order.** It's the fastest
> way to the mental model. Don't start from the code — start from `CLAUDE.md`.

---

## The strategy in three sentences

1. **Bias** — grade the current 5m session (`grade().strength`); if it's directional
   (|strength| ≥ 0.3), we have a side to trade.
2. **Setup** — inside that session, detect a 1m **consolidation** (a tight value area).
3. **Trigger** — when price breaks the consolidation's value-area edge *in the session's
   direction*, enter; stop = the opposite edge (1R); target = 2R.

The same `grade()` function measures both the 5m session and the 1m consolidation — that's
the "fractal" part. One engine, two scales.

---

## Start here (read in this order)

| # | File | Why |
|---|------|-----|
| 1 | **`CLAUDE.md`** | Architecture + conventions, and the **pipeline tier map** (bars → readings → snapshot → score → decide → manage). The mental model for everything else. |
| 2 | **`experiments/GRADE_SPEC.md`** | The **measurement engine**. How `grade()` scores any series on two axes — efficiency (net/travel) + acceptance (1−va_frac) — with frozen constants. This is the heart. |
| 3 | **`src/strategy/README.md`** | The strategy pipeline **as built** — the read-it-in-order view of the folders. |
| 4 | **`src/strategy/` code, in flow order** | `readings/structure.py` + `readings/consolidation.py` (facts) → `snapshot.py` (the contract) → `decide/va_breakout.py` (the rule) → `manage/fixed.py` + `manage/book.py` (lifecycle + state) → `pipeline.py` (wiring). |
| 5 | **`experiments/engine/out/validation_2024/README.md`** | The validation proof (2024: 271 trades, 55% win, **+0.49R** expectancy) — **read alongside the status note below.** |
| 6 | **`WORKFLOW.md`** | How the **three platforms** (Python · LEAN/QC · NinjaTrader) relate: the parity + cost/fill **contracts**, what's allowed to differ (execution model), and the `backtests/` **ledger** every run flows into. |
| 7 | **`NOTES.md`** (newest first) | Running log of decisions and what we learned. Essential context, including execution findings. |

**One-line pointer to paste elsewhere:**
> Read `CLAUDE.md` (architecture) and `experiments/GRADE_SPEC.md` (the grade engine), then
> `src/strategy/` in flow order (readings → snapshot → decide → manage). See the README's
> status note — the backtested edge is fill-dependent.

---

## ⚠️ Honest status — read before trusting any backtest number

The **paper/level-based backtest wins ~55–62%** (`+0.49R` in 2024) — but that assumes fills
*at* the value-area edge, which is physically unachievable (by the time a bar confirms a
break, price is already past the level). Ported to **QuantConnect with realistic execution**,
the same setups produce:

| Execution | Win rate | Result |
|-----------|----------|--------|
| Paper (fill-at-level) | ~55–62% | +0.49R / paper edge |
| QC market order (fill past the break) | **43%** | ~+1.2%/yr, marginal |
| QC stop order (fill on the poke) | **14%** | worse — noise-triggered |

**The edge is a fill mirage** until proven otherwise. Known open fix: a **min value-area-width
filter** — 56% of the stop-order losers are 1–2-tick "consolidations" that are pure noise.
The measurement engine (grade, sessions, consolidation) is solid; the *entry execution* is
what's under investigation.

---

## Repo map

```
src/            the backend "brain" (Python)
  indicators/     pure math (POC, MA, volume, ATR) — shared with the chart
  strategy/       the pipeline: readings → snapshot → score → decide → manage
  backtest/       runner + report (bounded-window validation; NOT 10-yr sweeps)
  brokers/        broker abstraction + adapters (execution seam; future)
chart/          the frontend — a thin view that renders what the backend computes
  server.py       the seam: serves the page + API, imports from src/
data/           datasets + pipeline (parquets gitignored)
experiments/    research: the frozen grade engine + GRADE_SPEC + validation output
lean/           QuantConnect LEAN ports (vabreakout = Python, vabreakout_cs = C#)
ninjatrader/    NinjaTrader 8 port (VABreakout.cs) + NT_AI_BRIEF.md (the NT contract)
backtests/      the run ledger: runs/<id>/ (trades+meta) + analyze/compare/import_qc + registry
tools/          replay_monitor (watch the pipeline bar-by-bar), csverify (Py↔LEAN↔NT gate)
algo_config.yaml  every tunable knob (read live per-request); see algo_config.README.md
```

> **How the three implementations (Python · QuantConnect · NinjaTrader) are wired together —
> where each lives, how each runs, and where every backtest is saved — is in
> [`ARCHITECTURE.md`](ARCHITECTURE.md).** Read it before touching the NinjaTrader side (it
> documents the Custom-folder compile path and the run-capture contract).

---

## Run it

```python
# the pipeline on recent bars
from src.strategy import pipeline
import pandas as pd
df = pd.read_parquet("data/NQ/NQ_5m.parquet").tail(2000)
pipeline.run(df, "NQ", "5m")     # -> {snapshot, scores, intent, action}
```

```bash
# bounded backtest + equity report (validation windows, not decade sweeps)
python -m src.backtest.report --start 2024-01-01 --save experiments/engine/out/pipeline_run

# the chart + live replay
python chart/server.py            # then open the served page
python tools/replay_monitor.py    # watch the pipeline decide, bar-by-bar

# 10-year sweeps: use the C# LEAN port (~34s), not the local runner (too slow)
```
