# The engine — how it works (and why you don't touch it)

Implements `experiments/GRADE_SPEC.md`: **one measurement (`grade`) applied to any
container (`anchor`) at any scale, recursively (`layers`), then rendered (`viz`).**
Same function at every zoom → no drift → the fractal property actually holds.

---

## ⚠️ FROZEN — do not edit these files

`grade.py`, `anchors.py`, `layers.py` are the **foundation**, exactly like
`src/indicators/range_hop.py`. They are proven (see the `validate_*.py` scripts) and
every scale depends on them being identical. **Changing a formula here silently changes
every layer at once and breaks the no-drift guarantee** — the whole point of the design.

- Want a new measurement? It probably belongs as a *derived* field or a new view, not a
  changed formula. Think hard before touching `grade()`.
- Want different structure detection? Add a new anchor function beside the existing
  ones; don't rewrite `impulse_anchors`.
- Want a new picture? Add a view file (like `cascade.py`) that *calls* the engine.

Extend at the edges (new views, new anchor types). Never edit the core.

---

## The pieces

| file | role | never-edit? |
|---|---|---|
| `grade.py` | `grade(bars) -> Grade` — the ONE measurement (full metric set) | **frozen** |
| `anchors.py` | `session_anchors` (clock) · `impulse_anchors` (structure) · `meta_frame` | **frozen** |
| `layers.py` | `descend` (zoom in) · `ascend` (zoom out) — the recursion | **frozen** |
| `viz.py` | shared drawing (candles / boxes / profile / grade box / ribbon) | extend only |
| `run.py`, `cascade.py` | views (consumers) | free to add |
| `validate_*.py` | the proofs | keep |

## How a read happens (data flow)

```
OHLCV bars  ─►  grade(bars) ─► Grade { direction, strength, efficiency, acceptance,
                                       profile(poc/vah/val), swings, wicks, delta,
                                       state, meta-candle }
```
- **anchors** decide *what bars* to grade: a session (clock-given) or an impulse
  (structure-detected = rolling `grade()` → IMPULSE runs, same-direction bursts merged
  across small gaps). `meta_frame` collapses a list of grades into OHLCV meta-candles.
- **layers** wire it across scale:
  - `descend(bars)` → grade it, then recurse into its IMPULSE sub-anchors (session →
    impulses → sub-impulses).
  - `ascend(units)` → grade each unit, collapse to meta-candles, grade the sequence
    (sessions → one multi-session grade).

## The one loop (the whole design in a sentence)

> Grade an anchor → its IMPULSE runs are the sub-anchors → grade those → recurse.
> Zoom out = collapse to meta-candles and grade. **Same `grade()` everywhere.**

## The knobs (tuning only — NOT structure)

In `grade.py`: `N_ROWS` (profile resolution), `E_CUT` (efficiency = directional),
`A_CUT` (acceptance = fat POC), `MIN_BARS` (below → UNCLEAR). In `anchors.py`:
`window`, `gap`, `min_len`. These are *thresholds*, safe to tune (eventually move to
`algo_config.yaml`). The *formulas* are frozen.

## The four states (× direction on the progress ones)

|                | acceptance < A_CUT (spread) | acceptance ≥ A_CUT (fat POC) |
|----------------|------------------------------|------------------------------|
| efficiency ≥ E_CUT | **IMPULSE** (up/dn)      | **GRIND** (up/dn) |
| efficiency < E_CUT | **WHIPSAW**              | **CONSOLIDATION** |

Plus **UNCLEAR** when the anchor is too small — the honest "no clean structure" state.

## Proofs (run these, don't trust prose)

- `validate_grade.py`   — grade() reproduces the Layer-1 anatomy numbers exactly.
- `validate_anchors.py` — impulse anchors match leg_states / the eye.
- `validate_layers.py`  — descend nests impulses; ascend turns 12 chop sessions into one clean trend.

## Views

- `run.py` → `drilldown.png` (grade numbers + impulse states + profile, unified) and
  `multiscale.png` (L3/L1/L2 regime ribbons over one chart).
- `cascade.py` → `cascade.png` (price within price within price: same format, each panel
  a zoomed-in piece of the one above).

## Open refinements (views/knobs, not core)

- Coarse ribbons should grade **meta-candles** (via `ascend`), not raw bars, so L3/L1
  light up instead of reading whipsaw.
- `E_CUT`/`A_CUT` likely want to be **scale-relative** (session-scale efficiency is low).
