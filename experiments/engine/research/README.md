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

## Status

Descriptive only — no entry/exit/stop/sizing rules yet. This is the **measure-what's-true**
phase; the edge (built on the `(L3, L1, L2)` triple + these transition tilts) comes after.
Heavier than the views (they touch 1m data + rolling grade), so they run on samples/windows.

### First edge-shaped observations (still descriptive)
- Down impulse → clean consolidation → **~60% reversal up** (accumulation base).
- Up impulse → any pause → **~60% continuation up**.
- Impulses die into whipsaw (~83%); NY-open is the impulse hotspot; clean higher-scale
  trends have *fewer* sub-impulses.
