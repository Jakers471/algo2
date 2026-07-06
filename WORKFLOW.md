# WORKFLOW — one strategy, three platforms, one ledger

How the **Python**, **QuantConnect/LEAN**, and **NinjaTrader** implementations of VABreakout
relate: what's shared, what's allowed to differ, the contracts that keep them honest, and the
`backtests/` ledger every run flows into. Read this after `CLAUDE.md` (architecture) and
`experiments/GRADE_SPEC.md` (the measurement engine).

---

## 1. The three implementations

| Impl | File | Role | Data reach | Fill honesty |
|------|------|------|-----------|--------------|
| **Python** | `src/strategy/` + `experiments/engine/grade.py` | **source of truth** + fast research baseline | full (local parquets) | paper (level fills) |
| **LEAN / QuantConnect** | `lean/vabreakout_cs/Main.cs` | cloud **long-history** validation | **2009 → now**, tick/second/minute (cloud) | honest at second/tick |
| **NinjaTrader 8** | `ninjatrader/VABreakout.cs` | **execution ground-truth** + path to live | **~2 yr** tick (local) | truest (Tick Replay) |

**One engine, three consumers.** All three run the *same* measurement engine (`grade()` +
consolidation detection). Python is the reference the other two are verified against. The
platforms exist for different *purposes*, not different strategies.

---

## 2. Contract A — signal/measurement parity (must be identical)

The **measurement math** is frozen and identical across all three. These constants never change
and are the same in every file:

```
NRows=24  StateWindow=25  MinLen=15  MaxAge=40  DetWindow=120  MinBars=8
ECut=0.38  ACut=0.55  BiasStr=0.3  TargetR=2.0
```

**Verified, not assumed.** `tools/csverify/` runs the LEAN (`Vab`, Span-based) and NinjaTrader
(`VabNt`, List-based) copies of `Grade` + `FindConsolidation` against the frozen Python source
over 52 windows. Green = `Python == LEAN == NT` (currently **52/52 consolidation + grade**).

> **Run this before shipping ANY change to the C# math:**
> ```
> python tools/csverify/export.py
> cd tools/csverify && dotnet run -c Release
> python tools/csverify/compare.py        # -> "LEAN 52/52 | NT 52/52 | ALL MATCH"
> ```

What csverify covers: **the measurement engine** — `grade()` (efficiency/acceptance → state,
strength, VAH/VAL/POC) and `FindConsolidation`. That's the risky, shared part.

---

## 3. Contract B — cost / fill (align, then label)

All engines use the **same costs** so numbers compare. Change one, change all three.

| Knob | Value | Where it's set |
|------|-------|----------------|
| Commission | **$4.00 / round turn** ($2/side) | Python `commission_rt=4.0` · QC fee model · NT Analyzer template |
| Slippage | **1 tick** per fill | Python `slip_ticks=1.0` · QC slippage model · NT Analyzer Slippage=1 |
| Sessions | **CT** boundaries | Python config · QC `SetTimeZone(Chicago)` · NT feed on CT clock |
| Primary bars | **Minute / 1** | all three (NT has a fail-fast guard) |

NQ multiplier: **$20 / point, $5 / tick.** Defaults live in `src/backtest/report.py`
(`commission_rt=4.0`, `slip_ticks=1.0`) and the NT brief — keep them in sync.

### Fill tiers by research phase (swap the fill model, never the signal)

| Phase | Fill model | Use |
|-------|-----------|-----|
| **Fast look** — "what's the strategy doing?" | `paper` / `minute` | quick iteration, optimistic |
| **Trusted number** — validation | `second` / `tick` | the number we act on |

**Fill-honesty ladder** (most → least honest): NT Tick-Replay ON  ▸  QC `Second`/`Tick`  ▸
QC/NT `Minute` (1-min OHLC approximation)  ▸  Python paper (level fills). Every run records
which tier it used in `meta.json` — a paper number and a tick number are **not** comparable and
`compare.py` flags the mismatch.

---

## 4. What's ALLOWED to differ — the entry-execution model

The **measurement** is identical (Contract A). The **entry execution** differs by platform, on
purpose — because that's exactly what we're studying (the "fill mirage"):

| Impl | Decider | Fill behavior |
|------|---------|---------------|
| **Python** | `Decide` — fires *after* price breaks the VA edge (`price > vah`) | paper: assumes a fill *at* the level → the optimistic ~55–62% number |
| **LEAN + NT** | `DecideArm` — arms a resting stop *before* the break (`price < vah`) | fills *at* the level on the break via a real stop order → honest |

So Python is the **paper/chase baseline**; the C# ports are the **honest resting-stop** version.
This divergence is intentional and is *not* covered by csverify (which only checks measurement).
When comparing runs, remember: Python-paper vs C#-resting-stop is an execution difference, not a
bug — and continuous-contract/roll differences between QC and NT are an unavoidable data residual
(labeled, not force-aligned).

---

## 5. The internal pipeline (shared shape)

Inside each impl the flow is the same one-directional pipeline (see `CLAUDE.md` for the full
tier map):

```
bars → indicators (grade math) → readings (facts) → snapshot (the contract)
     → score → decide → manage → broker/execution
```

The **Snapshot** is the stable contract; nothing downstream touches raw indicators. Stages
(score/decide/manage) are swappable named versions chosen in `algo_config.yaml`. The strategy
is **frozen** — we validate it, we don't tune it (see §7).

---

## 6. The ledger — `backtests/`

Every run from any engine lands here as a self-describing folder, and one analyzer reports them
all in the same vocabulary. See `backtests/README.md` for the schema.

```
backtests/
  runs/<run_id>/
    trades.csv | trades.json   # raw engine dump (NT=csv, QC=json)
    meta.json                  # THE LABEL (platform, bar type, tick_replay, commission,
                               #  slippage, fill_resolution, params snapshot, sample_type)
    report.md · equity.png     # generated
  analyze.py     # one run  -> report.md + equity.png + a registry row
  compare.py     # N runs   -> side-by-side, flags non-comparable cost/fill contracts
  import_qc.py   # QC ObjectStore trades JSON -> a labeled run
  registry.csv   # append-only index: one row per run (the at-a-glance compare)
```

**run_id:** `YYYY-MM-DD_<engine>_<fill>_NQ_<startYr>-<endYr>`
(e.g. `2026-07-06_nt_tick_NQ_2024-2026`).

**Stat vocabulary** (identical to the Python backtester): `trades · win% · expectancy R ·
total R · maxDD · profit factor · net $ · target-hit%`. R is computed when the run carries
per-trade stop/target (QC always; NT since the `Stop,Target,R` export; Python via the pipeline).
Because everything is scored in **R**, a commission-off run still lines up against a
commission-on one. `analyze.py` reads the **actual** commission column, so a run can't lie about
realized cost even if its label is stale.

### How a run gets into the ledger

- **NinjaTrader** — the strategy auto-writes `runs/<run_id>/{trades.csv, meta.json}` on
  `State.Terminated` (see `ninjatrader/NT_AI_BRIEF.md` §4). Then:
  `python backtests/analyze.py backtests/runs/<run_id>`
- **QuantConnect** — download the algo's ObjectStore `vabreakout_trades.json`, then:
  `python backtests/import_qc.py <that.json> --fill second --sample out_of_sample`
- **Python** — `python -m src.backtest.report --start … --save …` (bounded validation windows).

---

## 7. Validation stance — frozen ⇒ out-of-sample, not walk-forward

The strategy tunes **no parameters** (the constants in §2 are frozen), so there is nothing to
optimize and **walk-forward *optimization* does not apply yet**. What we do now is
**out-of-sample validation**: run the frozen strategy on periods it wasn't designed against and
confirm the edge survives.

- **In-sample (IS)** = data you tune on · **Out-of-sample (OOS)** = held-back data you only test on.
- **Walk-forward** = IS→OOS chained and rolled forward — a *tuning* procedure. Introduce it only
  if/when we deliberately choose knobs to optimize (which re-introduces overfit risk the frozen
  strategy currently doesn't have).

Label each run's `sample_type` (`full` / `in_sample` / `out_of_sample`) so the ledger records the
role a run played.

---

## 8. Stay-aligned checklist

- **Math change?** Re-run `tools/csverify` → `ALL MATCH` before shipping (§2).
- **NT source of truth** = `ninjatrader/VABreakout.cs` in the repo; symlink it into NT's
  `Custom\Strategies\` so there's no copy-paste drift (NT brief §6).
- **Cost/fill change?** Update all three + `src/backtest/report.py` defaults + the NT brief (§3).
- **New run?** It must carry a `meta.json`; run `analyze.py` so it enters `registry.csv`.
- **Comparing runs?** Check `compare.py`'s comparability warnings — don't compare across fill tiers.

## See also

- `CLAUDE.md` — architecture + the internal pipeline tier map
- `experiments/GRADE_SPEC.md` — the measurement engine (frozen constants)
- `backtests/README.md` — the ledger schema + analytics
- `ninjatrader/NT_AI_BRIEF.md` — the NinjaTrader contract (hand to the NT AI)
- `tools/csverify/README.md` — the Python ↔ LEAN ↔ NT equivalence harness
