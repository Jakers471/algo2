# vabreakout_cs — VA-breakout on LEAN, in C# (the fast one)

A C# port of `lean/vabreakout` (Python), for **speed**: compiled + no Python GIL, so it actually
uses the CPU and runs multi-year minute-data backtests in a fraction of the time. Same strategy,
same constants, same logic — just a different language.

## Why C# (per QC support)
Python on LEAN is single-threaded (GIL) — that's the hard ceiling on the Python algo's speed. C#
is compiled and native to LEAN, so the per-bar work is much cheaper and no numpy tricks are needed
(the plain profile loop is fast). Expect the 3-year run to drop from minutes to well under a minute.

## Files
- `Main.cs` — everything: the `QCAlgorithm` (continuous NQ, 5m consolidator, Chicago sessions,
  L1 bias + L2 consolidation break, 1m intrabar exits, ObjectStore checkpoint) **and** the strategy
  math (`Vab` static class: `Grade`, `FindConsolidation`, `Decide`) mirroring `grade_lib.py`.

## Run it
```bash
lean cloud push --project "vabreakout_cs" --force
lean cloud backtest "vabreakout_cs" --open
```
(Copy this folder into your LEAN workspace next to `vabreakout`, or it's already there if the repo's
`lean/` IS your workspace.)

## Status
Written from the LEAN C# API and mirrors the verified Python line-for-line, but **not compiled in
this environment** — the first `lean cloud backtest` may surface C# compile errors (type/API
specifics). Paste them and we fix fast; C# is stricter than Python so expect a couple of rounds.

## Verifying it matches
It logs the same throttled `running:` summary and saves trades to the ObjectStore key
`vabreakout_trades.json` — so we can pull its trades and diff them against the Python run's to
confirm the port is faithful.
