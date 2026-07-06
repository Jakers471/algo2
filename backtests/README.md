# backtests/ — one home for every run, one analytics engine

Each backtest — from **any** engine (NinjaTrader, QuantConnect, Python) — lands here as a
self-describing folder. One Python analyzer reads them all and reports in the **same
vocabulary**, so a NT-tick run and a QC-minute run compare apples-to-apples. This is the
"one source of truth for reporting" — engines capture their own rich analytics natively; this
layer is the **cross-engine, labeled, comparable** view.

## Layout

```
backtests/
  README.md          # this file
  analyze.py         # one run  -> report.md + equity.png (+ appends to registry.csv)
  compare.py         # N runs   -> side-by-side table
  registry.csv       # append-only index: one row per run (the at-a-glance compare)
  runs/
    <run_id>/
      trades.csv | trades.json   # raw engine dump (NT = csv, QC = json)
      meta.json                  # THE LABEL (see below)
      report.md                  # generated
      equity.png                 # generated
```

## run_id convention

`YYYY-MM-DD_<engine>_<fill>_NQ_<startYear>-<endYear>` — e.g.
`2026-07-06_nt_tick_NQ_2024-2026`, `2026-07-06_qc_second_NQ_2009-2026`. The label in the name
is a courtesy; `meta.json` is the authority.

## meta.json — every run is labeled with exactly how it was produced

```json
{
  "run_id": "...", "created_utc": "...",
  "platform": "ninjatrader | quantconnect | python",
  "instrument": "NQ", "bar_type": "Minute/1",
  "tick_replay": true, "fill_resolution": "tick | second | minute | paper",
  "commission_per_rt": 4.0, "slippage_ticks": 1,
  "requested_range": ["2015-01-01", "2026-07-05"],
  "params": { ...the frozen knobs... },
  "sample_type": "in_sample | out_of_sample | full",
  "notes": "..."
}
```

Two runs are only comparable when their **cost/fill contract matches** (commission, slippage,
fill resolution). `compare.py` flags mismatches so you don't compare a paper run to a tick run
by accident.

## The cost/fill contract (all engines align to this)

- **Commission:** $4.00 per round turn ($2/side). NQ: $20/pt, $5/tick.
- **Slippage:** 1 tick per fill.
- **Fill tiers (swap by research phase — signal never changes, only the fill model):**
  `paper`/`minute` = fast "what's it doing" look · `second`/`tick` = the honest number we trust.

These match `src/backtest/report.py` (`commission_rt=4.0`, `slip_ticks=1.0`) and the NT brief
(`ninjatrader/NT_AI_BRIEF.md`). Change one, change all three.

## Workflow

1. Run a backtest in NT or QC. The engine auto-saves `trades.*` + `meta.json` into a new
   `runs/<run_id>/` (NT: see the brief; QC: export from ObjectStore).
2. `python backtests/analyze.py runs/<run_id>` → writes `report.md` + `equity.png`, appends to
   `registry.csv`.
3. `python backtests/compare.py <run_id> <run_id> ...` → side-by-side.
4. Ad-hoc question about one run? Drop a `q_<name>.py` in its folder that reads
   `trades.csv`; keep the output next to the run. The universal report stays canonical.

## Stat vocabulary (identical to the Python backtester)

`trades · win% · expectancy R · total R · maxDD · profit factor · net $ · target-hit%`. R is
computed when the run carries per-trade stop/target (QC always; NT once its export includes
`Stop,Target,R` — see the brief). Without them, $/points still report.
