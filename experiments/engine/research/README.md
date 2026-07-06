# research/ — large-scale studies on the engine

These are **read-only research views**. They only *call* the frozen engine
(`../grade.py`, `../anchors.py`) and never modify it — they measure what's true across
years of data. Think of it as `break_sequence.py` (archived) grown up: instead of one
dimension (bull/bear) at one scale, the full 6-state vocabulary at three scales.

## The state vocabulary (same at every scale)

Two axes → four base states; two of them carry direction:

|                     | spread volume (low acceptance) | fat POC (high acceptance) |
|---------------------|--------------------------------|---------------------------|
| progress (went somewhere) | **IMPULSE** ↑/↓ (fast thrust)   | **GRIND** ↑/↓ (slow staircase) |
| no progress               | **WHIPSAW** (messy chop)        | **CONSOLIDATION** (clean range) |

Plus **UNCLEAR** (too few bars). Read at **L1** (session), **L2** (impulse), **L3**
(multi-session) → at any moment a triple `(L3, L1, L2)` = a 3-dimensional regime.

## Scale-relative cuts (important)

`grade()`'s absolute IMPULSE/etc. thresholds are tuned for the *fine* scale, so whole
sessions almost always read WHIPSAW. Since `grade()` also returns raw `efficiency` /
`acceptance`, these scripts re-classify each unit against **its own scale's
distribution** (percentile cuts). Frozen core untouched; only the *thresholds* move.

## The scripts

### `engine_stats.py` — L1 / L3 state sequences + cross-scale
State mix, what-follows-what, and run-lengths at L1 (session) and L3 (8-session meta),
plus the cross-scale co-occurrence (what 1m impulses fill each session state).

```bash
python experiments/engine/research/engine_stats.py
python experiments/engine/research/engine_stats.py --start 2020-01-01 --sample 200 --eff_pct 0.70
```
**Findings (NQ since 2022):**
- **L1 mean-reverts** — after *anything*, ~40% next session is CONSOLIDATION; directional
  sessions rarely repeat (IMPULSE UP → IMPULSE UP only 9%).
- **L3 trends** — regimes persist hard (IMPULSE UP → 76% stay bullish; CONSOLIDATION → 68%).
- **Persistence FLIPS with scale** — small scale reverts, large scale trends.
- **Cross-scale confirms the fractal** — directional sessions are built of directional
  impulses, chop of cancelling ones.

### `impulse_sequence.py` — L2 impulse event stream
The most direct descendant of break_sequence (impulses ARE the "breaks"). Direction
transitions, streaks, what sits between impulses, and impulse size by preceding state.

```bash
python experiments/engine/research/impulse_sequence.py
python experiments/engine/research/impulse_sequence.py --sessions 400
```
**Findings:**
- **Reproduces the break_sequence edge** — after an UP impulse, 57% continue up; after a
  DN impulse, 59% REVERSE up. Up streaks run longer (longest 9 vs 5). Up continues, down
  reverts — same asymmetry as the raw breaks, now on real impulses.
- **First impulse of a session is ~50% bigger** (opening drive: 29 vs ~20 pts).
- **Null result:** impulses born out of CONSOLIDATION are *not* bigger than out of WHIPSAW
  (both ~20 pts) — compression doesn't predict impulse *size* (maybe direction/cleanliness).

### `state_graphs.py` — general graphs across all scales (PNG)
Six-panel PNG (`out/state_graphs.png`): state mix by scale; impulses by session; impulses
by time of day (Chicago); what state follows an impulse; L2 impulses/session by L3 state;
sub-impulses inside an L1 impulse.
```bash
python experiments/engine/research/state_graphs.py            # 6 months (default)
```
**Findings (6mo):** consolidation/whipsaw dominate every scale (~65-70%); impulses peak at
the **NY open (9-10am CT)**; **an impulse is followed by WHIPSAW ~83%** (moves exhaust into
chop); when **L3 is impulsive there are FEWER sub-impulses** (clean trends run smooth; chop
= many cancelling impulses); an L1 impulse session is ~5:1 same-direction sub-impulses.

### `state_examples.py` — what WHIPSAW vs CONSOLIDATION look like (PNG)
3x2 grid (`out/state_examples.png`), scales x {whipsaw, consolidation}, each a real example
with its volume profile. Both go nowhere; the **profile** separates them — consolidation =
fat POC (acc ~0.7), whipsaw = spread/thin (acc ~0.2-0.3). Same signature at all 3 scales.

### `state_grids.py` — 3 examples per condition, per scale (PNGs)
One PNG per scale (`out/state_grid_L1.png`, `_L2`, `_L3`): the 6 states down the rows, 3
real examples across, each with its volume profile. The full vocabulary as real price —
reading down a column, efficiency drops (directional → flat) and the profile fattens/thins
by acceptance (impulse = spread, grind/consolidation = fat POC).
```bash
python experiments/engine/research/state_grids.py
```

### `sequence_patterns.py` — impulse -> pause -> ? (edge-shaped)
The 3-step pattern: does a trend continue after a pause, split by clean (consolidation) vs
noisy (whipsaw)? Bar PNG (`out/sequence_patterns.png`) + plain-english.
```bash
python experiments/engine/research/sequence_patterns.py --sessions 300
```
**Findings:** the up-continues/down-reverts asymmetry appears a THIRD time. **UP impulse →
~60% continue** (pause type doesn't matter). **DN impulse → reverses**, and a **clean
CONSOLIDATION after a down move → 60% reversal UP** (the strongest, most tradeable cell) vs
a whipsaw pause = coinflip. So the *pause type* is a real filter, but only for bears.

### `find_continuation.py` — up-leg -> consolidation -> up-leg (connected)
Searches for a CONNECTED bullish continuation at each scale — (impulse/grind up) ->
consolidation -> (impulse/grind up), phases contiguous — and draws the clearest example
per scale with the 3 phases shaded (`out/continuation_examples.png`). Found at all three
scales (L3 multi-session, L1 3-session, L2 impulse->base->impulse). The consolidation box
is the entry zone; the same structure recurs fractally.
```bash
python experiments/engine/research/find_continuation.py
```

### `alignment.py` — do the scales line up? (nesting/confluence)
Cross-scale directional alignment: when the higher scale is directional, does the lower
scale point the same way inside it? Bar PNG (`out/alignment.png`) + plain-english.
```bash
python experiments/engine/research/alignment.py --start 2023-01-01 --sample 200
```
**Findings — alignment COLLAPSES with scale distance:**
- **L1 -> L2 tightly coupled** (~86-88%): a directional session is built of same-direction
  impulses. Adjacent scales nest cleanly.
- **L3 -> L1 basically decoupled** (~19% aligned = the base rate): the L1 session mix is
  ~the same whatever L3 is doing. A multi-session trend is built through mostly-flat
  sessions (~68%) with occasional aligned pushes — it accumulates, it doesn't require each
  session to trend.
- **Full 3-scale confluence only ~18%** of directional moments -> rare and premium.
So setups nest partially: L2-in-L1 yes, L1-in-L3 no. "Trade with the big trend" fails at
the session level ~80% of the time; the value is that all-three-aligned is *rare*.

## Status

Descriptive only — no entry/exit/stop/sizing rules yet. This is the **measure-what's-true**
phase; the edge (built on the `(L3, L1, L2)` triple + these transition tilts) comes after.
Heavier than the views (they touch 1m data + rolling grade), so they run on samples/windows.

### First edge-shaped observations (still descriptive)
- Down impulse → clean consolidation → **~60% reversal up** (accumulation base).
- Up impulse → any pause → **~60% continuation up**.
- Impulses die into whipsaw (~83%); NY-open is the impulse hotspot; clean higher-scale
  trends have *fewer* sub-impulses.

### `backtest_cont.py` — FIRST edge test (value-area breakout in a directional session)
The trade rule: at a 1m CONSOLIDATION inside a session that is directional *so far* (net/range
bias, no lookahead), enter on the VAH/VAL break in the session direction, stop = opposite VA
edge (risk = VA height), target 2R, exit at session close. `out/backtest_cont.png`.
```bash
python experiments/engine/research/backtest_cont.py --sessions 300
```
**Result (300 sessions, NQ):** the rule = **37 trades, 54% win, +0.59R expectancy** (49% hit
+2R, 38% stopped). The session-bias filter roughly DOUBLES the edge vs an unfiltered control
(+0.59R vs +0.35R) — trading breakouts *with* the session beats all breakouts, as the L1<->L2
alignment predicted. CAVEATS: small sample (37), OPTIMISTIC fills (no slippage/commission),
single parameter set. A strong hypothesis to harden (bigger sample + real costs), not a system.

### `backtest_trades.py` — draw the real winners and losers (PNG)
The same rule, but records each trade and plots a grid of winners (left) / losers (right):
consolidation box, VAH/VAL, entry marker, stop (red), 2R target (green), exit. Shows the
bimodal reality — winners follow through to +2R, losers are FALSE BREAKOUTS that reverse back
through the value area to the stop. `out/backtest_trades.png`.
```bash
python experiments/engine/research/backtest_trades.py --sessions 200
```

### `backtest_equity.py` — MULTI-YEAR equity curve + management sweep (PNG)
The rule over 5 years (all sessions since --start), drawn as a cumulative-R equity curve under
four management variants: {2R, 3R} x {hard stop, breakeven-at-1R (stop -> entry once +1R hit)}.
Same trade set across variants so the curves are comparable. `out/backtest_equity.png`.
```bash
python experiments/engine/research/backtest_equity.py --start 2020-01-01
```
**Result (5 years, 2020->2025, 530 trades):** the edge is DURABLE — every variant grinds up
through COVID, the 2022 bear, and the 2024 bull, no multi-year dead zone. Honest larger-sample
expectancy **+0.46R** (down from +0.59R on the 37-trade sample). Findings:
- **2R beats 3R** — +0.46R / +243R / -6.7R DD vs 3R's +0.32R / +170R / -12.7R DD. Intraday
  exit-at-close means price runs out of session before 3R too often; the wider target doesn't pay.
- **Breakeven@1R is a wash on expectancy, a win on drawdown.** On 2R: identical money (+0.46R),
  it just swaps ~half the losses for scratches (32% scratch) and clips some runners — net zero.
  On 3R: it lifts expectancy (+0.36) and HALVES drawdown (-7 vs -12.7). Its real value is DD, not R.
- **Best config = 2R**; hard stop (51% win) vs breakeven (smoother, fewer full losses) is preference.
CAVEAT unchanged: optimistic fills; ~2 trades/week, a couple ticks of cost -> ~+0.38R, still positive.

### `backtest_excursion.py` — MAE/MFE analysis + trade CACHE (PNG)
Caches the 530-trade set to `out/trades_cache_*.pkl` (gitignored) so this and all later
management experiments run INSTANTLY (no 1m re-grading). Per-trade MAE (adverse heat before
exit) and MFE (favorable run), split winners/losers + long/short. `out/backtest_excursion.png`.
```bash
python experiments/engine/research/backtest_excursion.py --start 2020-01-01
```
**Findings (5yr, 530 trades):** edge is SYMMETRIC (long 323 @ 51% / short 207 @ 52%). Winners
take almost no heat (mean 0.29R, p90 0.77R, **max 0.98R**); losers all exceed 1R -> the 1.0R
stop is too wide. Full favorable run is big (median 3.0R, winners ~4R, tail to 40R) -> the 2R
target caps the tail, but a fixed 3R hurt (see equity) -> needs a trailing tool, not a wider target.

### `backtest_manage.py` — stop sweep + trailing runner (from cache, PNG)
Two management experiments off the cache (instant): (1) STOP SWEEP - 2R target fixed, stop moved
to 0.7/0.8/0.9/1.0 x VA, risk-normalized (loss -1R, win 2/f R); (2) TRAILING RUNNER - half off at
2R + trail the rest by 1R, vs fixed 2R. Both drawn as equity curves. `out/backtest_manage.png`.
```bash
python experiments/engine/research/backtest_manage.py
```
**Findings:**
- **Tighter stop wins (the MAE prediction).** 0.8R stop = the sweet spot: exp **+0.57R** (+24% over
  1.0R's +0.46), total +301R, and LOWER drawdown (-6.5 vs -6.7). 0.7R ties on expectancy but is
  choppier (DD -9.7) from extra stop-outs. **Adopt the 0.8R stop** - one number, free improvement.
- **Trailing runner = a WASH** (+243R both, identical curve). The MFE tail is real but "half@2R +
  trail 1R" is too loose to harvest it: trades that tag 2R then reverse give back on the trailed
  half exactly what the real runners gain. Capturing the tail needs a tighter trail (open follow-up).

### `backtest_costs.py` — net-of-costs equity (from cache, PNG)
Subtracts realistic NQ costs per trade, in R. NQ E-mini = $20/pt, tick 0.25pt=$5. Cost model
(round turn): commission ($, default 4) + slippage (ticks/side, default 1) -> a FIXED points
cost, expressed as R = cost_pts / (that trade's risk in pts), so tight-VA trades pay more R.
Compares 1.0R vs 0.8R stop, gross vs net. `out/backtest_costs.png`.
```bash
python experiments/engine/research/backtest_costs.py --commission_rt 4 --slip_ticks 1
```
**Findings ($4 comm + 1 tick/side = 0.70pt/$14 RT):** the edge SURVIVES costs. Avg risk (VA
width) is 12.3 pts (~$246), so $14 RT is only ~6% of risk -> costs shave ~0.10-0.12R/trade.
**0.8R stop stays best net: +0.44R exp (vs 1.0R's +0.36), +236R over 5yr, -8R DD.** Note VA
width ranges 1.2 -> 79.5 pts; on tiny bases the fixed cost is ~0.5R -> a MIN-VA filter (skip
consolidations < ~4-5 pts) should lift net further (open follow-up).

### Net-of-costs bottom line (strategy as it stands)
VA breakout, 0.8R stop, 2R target: **~+0.44R/trade net, ~106 trades/yr, +236R / 5yr, -8R maxDD**,
after $14/RT costs. Balanced long/short (51%/52%), durable across COVID / 2022 bear / 2024 bull.
Still research (experiments/), not yet in src/strategy/. Open: min-VA filter, tighter trail.
