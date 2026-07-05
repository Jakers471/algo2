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

## Status

Descriptive only — no entry/exit/stop/sizing rules yet. This is the **measure-what's-true**
phase; the edge (built on the `(L3, L1, L2)` triple) comes after. Heavier than the views
(they touch 1m data + rolling grade), so they run on samples where noted.
