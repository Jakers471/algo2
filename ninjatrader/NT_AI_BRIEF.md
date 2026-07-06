# NinjaTrader 8 — VABreakout: brief for the NT AI assistant

**Hand this whole file to the NinjaTrader AI.** It is the contract that keeps the NT8
implementation on the same page as the two other implementations of this strategy. Read it
top to bottom before touching `VABreakout.cs`.

---

## 0. What this is (one paragraph)

A fractal **volume-profile "VA-breakout"** day-trading strategy for **NQ** futures. It lives in
**three** places that MUST behave identically at the signal level:

| Impl | File | Role |
|------|------|------|
| **Python** (source of truth) | `src/strategy/` + `experiments/engine/grade.py` | the reference math; everything is verified against this |
| **QuantConnect C#** | `lean/vabreakout_cs/Main.cs` | cloud, long-history (2009→now) validation |
| **NinjaTrader 8 C#** | `ninjatrader/VABreakout.cs` | **your file** — execution ground-truth (Tick Replay) + path to live |

The **logic is frozen** — we are NOT optimizing parameters. Do not "improve," retune, or
add parameters to the strategy math. Your job is to keep NT faithful and to make its
backtests honest and well-captured. If you think the math is wrong, flag it — do not change it.

---

## 1. THE GOLDEN RULE — signal parity

The strategy math (`Grade`, `FindConsolidation`, `ValueArea`, `DecideArm`) in `VABreakout.cs`
must produce **byte-identical** signals to the Python source of truth. These constants are
**frozen** and identical across all three files — never change them:

```
NRows=24  StateWindow=25  MinLen=15  MaxAge=40  DetWindow=120  MinBars=8
ECut=0.38  ACut=0.55  BiasStr=0.3  TargetR=2.0
```

- L1 = 5m **session** bias = `Grade(full session buffer).Strength`; directional if `|strength| ≥ 0.3`.
- L2 = a 1m **CONSOLIDATION** (tight value area) found in the last `DetWindow` 1m bars.
- **Entry:** ARM a resting stop at the consolidation's value-area edge **in the session's
  direction** (`DecideArm`), so we fill AT the level on the break (never chase with a market order).
- **Stop:** opposite VA edge (risk = VA height = 1R). **Target:** `TargetR` × risk (2R).

If you change any math, it must still pass the equivalence harness in
`tools/csverify/` (see §6). Do not ship math changes that don't pass it.

---

## 2. NT CONFIG CONTRACT — the Strategy Analyzer setup (non-negotiable)

These settings are REQUIRED. A wrong one silently produces a different strategy (we already
lost a run to 150-tick bars). Enforce them:

| Setting | Required value | Why |
|---------|----------------|-----|
| **Primary Data Series → Type/Value** | **Minute / 1** | all bar-count windows (`StateWindow`, `DetWindow`, …) count 1-min bars. **Tick bars corrupt the timescale.** |
| Added series | 5-Minute (added in `State.Configure`) | the 5m session bias stream (BarsInProgress==1) |
| **Tick Replay** | **ON** | honest intrabar fills for the resting stop entry + bracket exits (this is the whole point of NT here) |
| Timezone | bars on **Chicago/CT** clock | `SessionOf()` thresholds assume CT. If your feed is ET, shift each boundary +1h (18→19, 3→4, 8→9, 17→18) |
| Calculate | `OnBarClose` | decisions on the 5m close (correct by design) |
| EntriesPerDirection | 1 | one position at a time |

**Add a fail-fast guard** in `State.Configure`: if the primary series is not Minute/1, throw
with a clear message (`"VABreakout requires a 1-Minute primary series, got <X>"`) so a
misconfigured run can never silently produce garbage again.

---

## 3. COST / FILL CONTRACT — align to the other frameworks

All three frameworks use the **same** costs so their numbers are comparable. Do not run
commission-off "for convenience" — an unlabeled cost setting is how we got contradictory
results.

| Cost | Value | NT how-to |
|------|-------|-----------|
| **Commission** | **$4.00 per round turn** ($2.00 / side) | Strategy Analyzer → Commission template = custom $2/side (or NinjaTrader Brokerage if it matches) — must be **ON** |
| **Slippage** | **1 tick per fill** | Strategy Analyzer → Slippage = 1 (NQ tick = 0.25pt = $5) |
| Fill realism | Tick Replay ON | see §2 |

NQ multiplier: **$20 / point, $5 / tick.** These match the Python cost model
(`commission_rt=4.0`, `slip_ticks=1.0`) — keep them in sync if Python changes.

**Fill tiers by research phase** (we swap the *fill model*, never the signal):
- **Fast look** ("what is the strategy doing?"): Tick Replay OFF is fine — quick, optimistic.
- **Honest number** (validation): Tick Replay ON — the number we trust.
Label which one every run used (see §4).

---

## 4. EXPORT CONTRACT — capture every trade into the repo

Every backtest must auto-save into the repo's organized folder so our Python analytics can
read it. **Save location changes from Desktop to the repo:**

```
<repo>/backtests/runs/<run_id>/
    trades.csv     # one row per round-trip trade (schema below)
    meta.json      # the label — what this run WAS
```

- `<repo>` = `C:\Users\jakers\Desktop\volume_profile_algo`. `<run_id>` =
  `YYYY-MM-DD_nt_<fill>_NQ_<startYear>-<endYear>` (e.g. `2026-07-06_nt_tick_NQ_2024-2026`).
  Use a millisecond timestamp in the folder name if a collision is possible.

**trades.csv columns** (KEEP these, and ADD the three marked ⭐ so we can score in R):

```
TradeNumber,Instrument,Direction,Quantity,EntryTime,EntryPrice,EntryName,
ExitTime,ExitPrice,ExitName,ProfitPoints,ProfitTicks,ProfitCurrency,Commission,
CumProfitCurrency,MaePoints,MfePoints,⭐Stop,⭐Target,⭐R
```

⭐ **Stop, Target, R are new and important.** `SystemPerformance.AllTrades` does NOT carry the
strategy's stop/target, so track them yourself: keep a per-position record of
`(entry, stop, target, direction)` captured in `OnExecutionUpdate` when the entry fills
(you already have `_arm` there), and on the exit compute
`R = (exit - entry)/|entry - stop| * (long?+1:-1)`. Export that record. This mirrors the QC
port's `TradeRec {entry, stop, target, exit, R}` exactly — do it the same way so the two line up.

**meta.json** (write this every run — it is the label that makes the run comparable):

```json
{
  "run_id": "2026-07-06_nt_tick_NQ_2024-2026",
  "created_utc": "2026-07-06T12:25:15Z",
  "platform": "ninjatrader",
  "strategy": "VABreakout",
  "instrument": "NQ",
  "bar_type": "Minute/1",
  "tick_replay": true,
  "fill_resolution": "tick",
  "commission_per_rt": 4.0,
  "slippage_ticks": 1,
  "requested_range": ["2015-01-01", "2026-07-05"],
  "params": {"NRows":24,"StateWindow":25,"MinLen":15,"MaxAge":40,"DetWindow":120,
             "MinBars":8,"ECut":0.38,"ACut":0.55,"BiasStr":0.3,"TargetR":2.0},
  "sample_type": "out_of_sample",
  "notes": "tick data only reaches back ~2 yr, so actual trades start 2024-03"
}
```

Write `meta.json` in `State.Terminated` alongside the CSV. Record the **requested** range;
our analytics fills in the **actual** first/last trade dates.

---

## 5. KNOWN NT8 GOTCHAS (already in the file header — do not regress)

- **Namespace:** strategies MUST be in `NinjaTrader.NinjaScript.Strategies`. Do NOT add a
  trailing `.NinjaTrader` segment — it shadows the root namespace and breaks the whole Custom
  assembly.
- **No `Span`/`stackalloc`:** NT8 is .NET Framework and may lack `System.Memory`. `Grade`
  takes `(List, start, len)` and reuses the `_bin` scratch array — keep it allocation-free, no LINQ.
- **Exits are REAL orders** (`SetStopLoss`/`SetProfitTarget`), not a manual bar-OHLC check.
  Under Tick Replay these fill honestly — that is the fix for the "fill mirage." Keep it.
- **Session/gap:** a >30-min bar gap breaks the session (so day1..day2 don't merge). Keep it.

---

## 6. STAY-ALIGNED WORKFLOW

**The repo file `ninjatrader/VABreakout.cs` is the source of truth for the NT version.**
NinjaTrader compiles from `Documents\NinjaTrader 8\bin\Custom\Strategies\`. Two ways to avoid
copy-paste drift (pick one):

1. **Symlink (best):** link the repo file into NT's folder so editing the repo == editing NT:
   ```powershell
   New-Item -ItemType SymbolicLink `
     -Path "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\Strategies\VABreakout.cs" `
     -Target "C:\Users\jakers\Desktop\volume_profile_algo\ninjatrader\VABreakout.cs"
   ```
   Then just recompile in NT (F5 in the NinjaScript Editor) after any change.
2. **Copy on change:** copy the repo file into the Strategies folder whenever it changes.

**Before shipping any change to the strategy math**, the human runs the equivalence harness
(`tools/csverify/`) — it proves the C# math matches Python. NT's copy of the math should be
added as a third target there; until it is, eyeball-match NT's `Grade`/`FindConsolidation`
against `Main.cs` (they should be line-for-line identical except List-vs-Span).

---

## 7. YOUR CHECKLIST (what "done" looks like for an NT change)

- [ ] Math constants unchanged and identical to `Main.cs` (§1)
- [ ] Fail-fast guard rejects non-Minute/1 primary (§2)
- [ ] Commission $4/RT + 1-tick slippage wired and ON (§3)
- [ ] Per-trade Stop/Target/R tracked and exported (§4)
- [ ] trades.csv + meta.json auto-saved into `backtests/runs/<run_id>/` (§4)
- [ ] No namespace/Span/exit-order regressions (§5)
- [ ] Compiles clean in the NinjaScript Editor
