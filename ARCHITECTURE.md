# ARCHITECTURE — the three-way setup (Python · QuantConnect · NinjaTrader 8)

How the same strategy lives in three places, how they stay in sync, and where every backtest
is saved. If you only read one thing about *wiring* (not strategy logic), read this.

> Strategy logic lives in `README.md` + `CLAUDE.md` + `experiments/GRADE_SPEC.md`.
> This doc is about **plumbing**: what runs where, and where the numbers land.

---

## TL;DR mental model

- **One strategy, three implementations.** The math is **frozen and identical** in all three.
  Python is the **source of truth**; the other two must match it at the signal level.
- **One reporting layer.** Every run — no matter which engine — saves into
  `backtests/runs/<run_id>/` as `trades.csv` + `meta.json`, and `backtests/analyze.py` reads
  them all in the same vocabulary. Apples-to-apples.
- **Differences between engines are allowed only in data + execution** (continuous-contract
  build, fills, costs) — never in signal math. `tools/csverify/` is the gate that proves it.

```
                         ┌──────────────────────────────┐
   SIGNAL MATH (frozen)  │  grade / consolidation / VA / │   proven identical by
   NRows=24 … TargetR=2  │  decideArm                    │   tools/csverify (52/52)
                         └──────────────────────────────┘
                                     │  same logic, three hosts
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
   ┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
   │ PYTHON          │     │ QUANTCONNECT/LEAN │     │ NINJATRADER 8         │
   │ source of truth │     │ long-history val. │     │ execution ground-truth│
   │ src/strategy/   │     │ lean/vabreakout_cs│     │ ninjatrader/          │
   └────────┬────────┘     └─────────┬────────┘     └──────────┬───────────┘
            │  trades + meta          │  trades + meta          │  trades.csv + meta.json
            └─────────────────────────┼─────────────────────────┘
                                      ▼
                        backtests/runs/<run_id>/   →   analyze.py → report.md + equity.png
                                      ▲
                              registry.csv (append-only index of every run)
```

---

## The three implementations

| | **Python** | **QuantConnect (LEAN)** | **NinjaTrader 8** |
|---|---|---|---|
| **Role** | Reference math; source of truth | Cloud, long-history (2009→now) validation | Execution ground-truth (Tick Replay) + path to live |
| **Lives in** | `src/strategy/` + `experiments/engine/grade.py` | `lean/vabreakout_cs/Main.cs` | `ninjatrader/VABreakout.cs` (+ `TradeExporter.cs`) |
| **Language** | Python | C# (LEAN) | C# (NinjaScript) |
| **Runs via** | `python -m src.backtest.report …` / `pipeline.run(...)` | LEAN CLI / QC cloud (~34s for 10yr) | NinjaTrader **Strategy Analyzer** (GUI) |
| **Fill realism** | paper (fill-at-level, optimistic) | market/stop/second-bar models | **Tick Replay** (honest intrabar) |
| **Saves** | `trades` + `meta.json` → `backtests/runs/` | `trades.json` + `meta` (via `backtests/import_qc.py`) | `trades.csv` + `meta.json` → `backtests/runs/` (auto, from the strategy) |
| **Best for** | fast logic iteration, the truth to match | decade-scale robustness | real fills, forward test, eventually live |

---

## Where the strategy physically lives (and the NinjaTrader gotcha)

### Python & QC — simple
They run **from the repo**. Edit `src/strategy/…` or `lean/vabreakout_cs/Main.cs` in place and run.

### NinjaTrader — NOT simple (read this)
NinjaTrader **does not compile from the repo.** It compiles **everything** under one folder
into a single assembly (`NinjaTrader.Custom.dll`):

```
C:\Users\jakers\Documents\NinjaTrader 8\bin\Custom\
    Strategies\VABreakout\VABreakout.cs      ← the strategy (pure trading logic)
    AddOns\Reporting\TradeExporter.cs        ← reusable run-capture (CSV + meta.json + checkpoints)
    Strategies\NinjaTrader\@Strategy.cs      ← NinjaTrader SYSTEM glue — do NOT delete (see note)
    …all of NinjaTrader's own built-ins…
```

- **Source of truth is still the repo**: `ninjatrader/VABreakout.cs` and
  `ninjatrader/TradeExporter.cs`. The copies under `…\Custom\…` are what NT actually builds.
- **Keep them in sync** (pick one):
  - **Symlink (best):** link the repo files into the Custom folder so editing the repo == editing NT.
    ```powershell
    New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\Strategies\VABreakout\VABreakout.cs" -Target "C:\Users\jakers\Desktop\volume_profile_algo\ninjatrader\VABreakout.cs"
    New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\AddOns\Reporting\TradeExporter.cs" -Target "C:\Users\jakers\Desktop\volume_profile_algo\ninjatrader\TradeExporter.cs"
    ```
  - **Copy on change:** copy both files into the Custom folder whenever they change.
- **Compile** = open the **NinjaScript Editor** in NinjaTrader and press **F5**. It builds the
  whole `Custom\` tree at once.
  - You can reproduce that exact compile *outside* NinjaTrader with
    `dotnet build "…\Custom\NinjaTrader.Custom.csproj" -c Release` — `0 Error(s)` there == clean F5.
- **⚠️ One-assembly consequences:**
  - A single broken `.cs` anywhere in `Custom\` fails the whole build.
  - **Never delete the `*\NinjaTrader\` folders** — those are NinjaTrader's own system files.
    Deleting `Strategies\NinjaTrader\@Strategy.cs` removes the `indicator` glue and produces
    hundreds of `"The name 'indicator' does not exist"` errors across NT's own files.
  - Keep other projects **out** of `Custom\` (or they compile — and can break — alongside this one).

---

## How runs are saved (the reporting contract)

Every engine drops a self-describing folder here; one analyzer reads them all. Full spec in
**`backtests/README.md`**.

```
backtests/
  analyze.py         # one run  -> report.md + equity.png  (+ appends registry.csv)
  compare.py         # N runs   -> side-by-side table
  import_qc.py       # pull a QuantConnect result into a run folder
  registry.csv       # append-only index, one row per run
  runs/
    <run_id>/
      trades.csv | trades.json   # raw engine dump (NT = csv, QC = json, Py = either)
      meta.json                  # THE LABEL — how the run was produced
      report.md   equity.png     # generated by analyze.py
```

- **`run_id`** = `YYYY-MM-DD_<engine>_<fill>_NQ_<startYr>-<endYr>`
  (e.g. `2026-07-06_nt_tick_NQ_2024-2026`). The name is a courtesy; **`meta.json` is the authority.**
- **`meta.json`** records platform, `bar_type`, `tick_replay`, `fill_resolution`,
  `commission_per_rt`, `slippage_ticks`, `requested_range`, the frozen `params`, `sample_type`,
  and `notes`. It's what makes an NT-tick run and a QC-minute run comparable.
- **NinjaTrader writes this automatically** from the strategy (`TradeExporter`), into
  `backtests/runs/<run_id>/` — no manual export. A partial checkpoint is written to
  `runs/_inprogress_nt/` every 10% so a stopped run isn't lost.
- **trades.csv schema (NT):** the standard columns **+ `Stop, Target, R`** — R is
  `(exit−entry)/|entry−stop|·dir`, matching QC's `TradeRec`. `analyze.py` scores in R off this.
- **Costs come from the data, not the label:** `analyze.py` sums the real `Commission` column,
  so the reported cost is always what actually ran regardless of what `meta.json` claims.

To analyze a run:
```bash
python backtests/analyze.py backtests/runs/<run_id>     # report.md + equity.png + registry row
python backtests/compare.py backtests/runs/<a> backtests/runs/<b>
```

---

## Signal parity — the gate that keeps all three honest

`tools/csverify/` proves the C# math equals the Python math. **Current status: 52/52 on both
`FindConsolidation` and `grade`, across Python == LEAN == NT.**

- The **frozen constants** (identical in all three, never change):
  `NRows=24 StateWindow=25 MinLen=15 MaxAge=40 DetWindow=120 MinBars=8 ECut=0.38 ACut=0.55 BiasStr=0.3 TargetR=2.0`.
- Golden rule: **do not "improve", retune, or add parameters to the strategy math.** If it
  looks wrong, flag it — don't change it. Any math change must re-pass `csverify`.
- Because signals are provably identical, **any NT-vs-QC difference is confined to data + fills +
  costs** — not logic.

---

## Cost contract (aligned across all three, so nets compare)

| Cost | Value | Notes |
|---|---|---|
| Commission | **$4.00 / round-turn** ($2.00/side) | NT: Commission template = custom **$2/side**, NQ per-unit = **2.00**. Python: `commission_rt=4.0`. |
| Slippage | **1 tick / fill** | NT: `Slippage=1` (enforced in code). NQ tick = 0.25 pt = $5. |
| Fills | honest | NT: **Tick Replay ON**; QC: second/tick model; Python: paper (optimistic — see README status note). |

NQ multiplier: **$20 / point, $5 / tick.**

---

## Data caveat (why the engines won't perfectly reconcile)

Each platform builds the **continuous NQ contract** differently (roll date + back-adjustment),
so historical prices differ (NT shows back-adjusted ~7,100 in 2015 vs the real ~4,200) → different
value areas → different signals. QC uses `BackwardsRatio` + `LastTradingDay`; NT uses its own.
**This divergence is structural, not a bug.** Also: NT **Tick Replay only has ~2yr of tick
history**, so an NT tick run's real trades start ~2024 regardless of the requested start.

---

## Quick reference — run each engine

```bash
# PYTHON — fast logic iteration (the truth)
python -m src.backtest.report --start 2024-01-01 --save experiments/engine/out/pipeline_run

# QUANTCONNECT — decade-scale validation (C# port), then import the result
python backtests/import_qc.py <qc-result>        # -> backtests/runs/<run_id>/

# NINJATRADER — Strategy Analyzer (GUI): Minute/1 primary, Tick Replay ON,
#   Commission = custom $2/side, Slippage = 1  ->  auto-saves backtests/runs/<run_id>/
#   then:
python backtests/analyze.py backtests/runs/<run_id>

# PARITY GATE — prove C# == Python before shipping any math change
#   (see tools/csverify/README.md)
```

## See also
- `README.md` — the strategy + honest status
- `CLAUDE.md` — architecture + pipeline tier map
- `experiments/GRADE_SPEC.md` — the measurement engine
- `backtests/README.md` — the run/reporting contract in full
- `ninjatrader/NT_AI_BRIEF.md` — the NinjaTrader build contract (frozen math, config, export)
- `tools/csverify/README.md` — the signal-parity harness
