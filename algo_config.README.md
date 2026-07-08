# algo_config.yaml — the config guide

This is the **single source of truth for every tunable knob** in the project.
The chart, the indicators, and the strategy pipeline all read their parameters
from here — so what you see on the chart is exactly what a backtest/strategy runs
on. Nothing numeric is hardcoded; if it's tunable, it lives here.

**It's read live.** The backend re-parses this file on every request, so you can
**edit a value and just refresh / re-run replay — no server restart.** (Only
changes to Python *code* need a restart; config values don't.)

Each section below maps 1:1 to a block in `algo_config.yaml`. `src/config.py`
exposes one accessor per block (e.g. `sessions_config()`), which is what the code
actually calls.

---

## `sessions` — the trading sessions

```yaml
sessions:
  timezone: America/Chicago
  max_sessions: 60
  windows:
    Asia:   { start: "18:00", end: "03:00", color: "#3f8ae0" }
    London: { start: "03:00", end: "08:00", color: "#e0a44e" }
    NY:     { start: "08:00", end: "17:00", color: "#a06ee0" }
```

Defines the Asia / London / NY sessions. Used by the **Sessions H/L** and **Volume
Profile** indicators (and everything downstream that knows about "the current
session," like the Snapshot).

- **`timezone`** — the clock the window times are in (DST-aware). `18:00` means 6pm
  *Chicago time*, adjusting automatically for daylight saving.
- **`max_sessions`** — how many recent session instances to compute/draw. Higher =
  more history on the chart (and more compute); lower = lighter.
- **`windows`** — each session's `start`/`end` (local `HH:MM`) and chart `color`.
  A window may **wrap past midnight** (Asia `18:00 → 03:00` spans the night). The
  windows here don't overlap; a bar is assigned to the first one it falls in.

Change a window's hours and every session-based level (session highs/lows, which
volume profile a bar belongs to) shifts with it.

---

## `volume_profile` — the per-session volume profile (POC / value area)

```yaml
volume_profile:
  row_size: 5.0
  value_area_pct: 0.50
```

For each session, buckets that session's volume **by price** to find where trade
concentrated. Produces POC / VAH / VAL — the levels you see in the SNAPSHOT.

- **`row_size`** — the price height of each bucket, in points (5.0 = every $5 of
  price is one row), anchored to an absolute grid so rows line up across sessions.
  **Smaller = finer resolution** (and can move the POC, since it's the single
  most-traded row). This is a *parameter of the computation*, not a display filter
  — the POC genuinely changes with it.
- **`value_area_pct`** — the fraction of session volume that defines the **value
  area**. `0.50` = expand out from the POC until the rows cover 50% of the volume;
  the block's edges are **VAL** (low) and **VAH** (high). Raise it (e.g. `0.70`)
  and the value area gets wider (VAH↑, VAL↓); POC is unaffected.

---

## `volume` — the time-based volume histogram (chart presentation only)

```yaml
volume:
  up_color: "rgba(25, 158, 112, 0.5)"
  down_color: "rgba(230, 103, 103, 0.5)"
  height_pct: 0.20
```

The plain volume bars under each candle. This block is **presentation only** — the
volume *math* has no knobs (a bar's volume is just its volume). These control how
the chart draws it:

- **`up_color` / `down_color`** — bar tint when the candle closed up / down.
- **`height_pct`** — fraction of the chart pane the volume band fills, pinned to the
  bottom (`0.20` = bottom 20%).

> Note: this is the chart's *time-based* volume. The strategy's volume **facts**
> (rvol/delta/vexp — see `strategy.readings` below) are derived from the same
> underlying per-bar volume but are a separate concern.

---

## `atr` — Average True Range (volatility) — *experimental*

```yaml
atr:
  period: 14
  color: "#eb6834"
  height_pct: 0.18
```

The smoothed *true range* per bar, in price points — a volatility magnitude, not a
price level, so it draws as a line in a **lower band** of the price pane (like a
MACD/RSI sub-panel would), toggled from the control panel (**off by default**).

- **`period`** — Wilder smoothing lookback in bars (14 = reacts like a 14-bar
  average range). **The only math knob** — read by `src.indicators.atr`; the chart
  and (later) the backtester both compute ATR from it, so it never drifts. Smaller
  = twitchier/more responsive; larger = smoother/slower.
- **`color`** — the line's chart color (presentation, read by the renderer).
- **`height_pct`** — how tall the lower band is, as a fraction of the pane. The band
  is shared with the volume histogram (v4 has no true sub-panes); toggle **Volume**
  off if you want the strip to itself.

Where it's read: `period` in `src/indicators/atr.py`; `color`/`height_pct` in
`chart/static/js/indicators/atr.js` (via `/api/config`). Served at
`/api/indicators/atr`.

---

## `moving_averages` — the MA lines

```yaml
moving_averages:
  source: close
  lines:
    - { type: sma, period: 20,  color: "#4fc3f7" }
    - { type: sma, period: 50,  color: "#ffb74d" }
    - { type: sma, period: 100, color: "#f06292" }
    - { type: sma, period: 200, color: "#ba68c8" }
```

- **`source`** — which price each MA averages: `close` / `open` / `high` / `low` /
  `hl2` ((H+L)/2) / `hlc3` / `ohlc4`.
- **`lines`** — one entry = one line on the chart. **Add or remove lines freely.**
  - **`type`** — `sma` (simple: plain average) or `ema` (exponential: weights recent
    bars more, so it hugs price closer and doesn't lag as hard).
  - **`period`** — lookback in bars (20 = average of the last 20 bars).
  - **`color`** — the line's chart color.

---

## `strategy` — the pipeline (versions + knobs)

```yaml
strategy:
  use:
    scorer:  v1
    decider: va_breakout
    manager: fixed
  readings:      { volume_window: 20, volume_fast: 3 }
  regime:        { n_rows: 24, e_cut: 0.38, a_cut: 0.55, min_bars: 8 }
  consolidation: { det_window: 120, state_window: 25, min_len: 15, max_age: 40 }
  decide:        { bias_str: 0.3, target_r: 2.0 }
```

Mirrors `src/strategy/` (`readings → snapshot → score → decide → manage`). See
`src/strategy/README.md` for the full pipeline. Every numeric knob the strategy runs
on lives here — edit + refresh retunes the readings/regime/trades with no restart
(defaults reproduce the prior hardcoded behaviour, so an unedited file is a no-op).

### `use` — which VERSION of each swappable stage runs

Each stage (`scorer` / `decider` / `manager`) is a folder of interchangeable
versions. These three lines pick which one is active. **Swap a stage by changing
one word** — e.g. `manager: fixed → trailing` — and nothing else moves. A
"strategy" is just a named combo of versions. `decider: va_breakout` and
`manager: fixed` carry live logic today (tuned by the `regime`/`consolidation`/`decide`
knobs below); the `scorer` slot is a pass-through until confluence scoring is added.

### `readings` — how the SNAPSHOT facts are derived

Knobs for turning raw indicator output into the facts in the Snapshot. Right now,
these are the **volume** lookback windows. (The regime/base/entry knobs live in the
three sections below.)

> **Important — one window feeds several facts.** `volume_window` is *not* just for
> one number. It is the shared **baseline lookback** used by **all** of the volume
> facts. Here's exactly how:

- **`volume_window: 20`** — the baseline / "what's normal lately" window, in bars.
  Three facts lean on it:
  - **`rvol`** = *this bar* ÷ **average of the last `volume_window` bars**. So
    `rvol` answers "is this bar bigger than the recent norm?" — and the "norm" is
    defined by this window.
  - **`delta`** = net signed volume summed **over the last `volume_window` bars**
    (up-bar volume minus down-bar volume) — recent buying vs selling pressure.
  - **`vexp`** = (fast average) ÷ **average of the last `volume_window` bars**. The
    window is `vexp`'s *denominator* — its baseline.

  So if you change `volume_window`, **rvol, delta, AND vexp all shift together**,
  because they all measure against this same baseline.

- **`volume_fast: 3`** — used **only by `vexp`**, as its *numerator*: the average of
  the last `volume_fast` bars (the short-term pulse). So:

  ```
  vexp = avg(last volume_fast bars)  ÷  avg(last volume_window bars)
          └──── "right now" ────┘         └──── "the baseline" ────┘
  ```

  `vexp ≈ 1` when recent volume matches the baseline (steady); `vexp > 1` and rising
  when recent bars are outpacing the baseline (volume *ramping up* — the "steady →
  boom" build that a single-bar `rvol` spike would miss).

**Tuning cheat-sheet:**

| Change | Effect |
|---|---|
| bigger `volume_window` | smoother/slower baseline; rvol & vexp react less to short bursts, compare against a longer "normal" |
| smaller `volume_window` | twitchier; compares against only very recent bars |
| bigger `volume_fast` | `vexp` smoother — needs a more *sustained* ramp to move |
| smaller `volume_fast` (=1) | `vexp` ≈ `rvol` — reacts to a single bar (loses the "build") |

On 5-minute bars: `volume_window: 20` ≈ 100 minutes of baseline; `volume_fast: 3` ≈
15 minutes of "right now."

> Edge case: at the very start of the data (fewer than `volume_window` bars exist),
> the averages use whatever bars are available — so the first ~20 readings run on a
> shorter baseline. Rarely matters (we load 10k bars), but that's the one caveat.

### `regime` — the GRADE state classifier's cutoffs

```yaml
strategy:
  regime:
    n_rows: 24
    e_cut: 0.38
    a_cut: 0.55
    min_bars: 8
```

These are the cutoffs the GRADE engine (`experiments/engine/grade.py`) uses to label a
window's **regime** — `IMPULSE` / `GRIND` (±direction) / `CONSOLIDATION` / `WHIPSAW` /
`UNCLEAR`. GRADE reduces any window to two axes and cross-cuts them:

```
              acceptance ≥ a_cut       acceptance < a_cut
efficiency ≥ e_cut   GRIND (up/dn)         IMPULSE (up/dn)
efficiency < e_cut   CONSOLIDATION         WHIPSAW
```

> **Important — one setting, both scales AND the trades.** These cutoffs run on **both**
> structure scales (L1 5m session *and* L2 1m window) and on the consolidation detector.
> The decider's bias filter reads the L1 `strength`, and the entry reads the L2
> `CONSOLIDATION` base — so changing a regime knob shifts the chart's regime coloring
> **and** which setups fire. This is the single biggest lever in the strategy.

- **`e_cut: 0.38`** — the **efficiency** cutoff. Efficiency = `|net| ÷ travel` (0..1): how
  *directly* price got where it ended (1 = a straight line, ~0 = churned in place). At or
  above `e_cut` the window is **directional** (IMPULSE/GRIND); below it is **choppy**
  (CONSOLIDATION/WHIPSAW). *Raise it* → fewer windows count as trends (stricter). *Lower it*
  → more do.
- **`a_cut: 0.55`** — the **acceptance** cutoff. Acceptance = `1 − value-area fraction`: how
  **fat** the POC is (how much of the range price actually accepted / built value in). High
  = value built (GRIND / CONSOLIDATION); low = thin, one-and-done (IMPULSE / WHIPSAW). *Raise
  it* → harder to call something "accepted."
- **`n_rows: 24`** — how many rows the volume profile is sliced into **per window**. Fixed
  count (not a price height) so `va_frac` — and therefore `acceptance` — is comparable
  across any scale. More rows = finer POC/value-area resolution (and can nudge acceptance).
- **`min_bars: 8`** — a window with fewer bars than this reads `UNCLEAR` (GRADE's honest "not
  enough structure to judge"). Raise it to demand more evidence before labelling a regime.

Tuning cheat-sheet:

| change | effect |
| --- | --- |
| raise `e_cut` | fewer IMPULSE/GRIND (trend) reads; more CONSOL/WHIPSAW — a stricter trend filter |
| lower `e_cut` | more windows read as directional (looser) |
| raise `a_cut` | more IMPULSE/WHIPSAW (thin); harder to read "value accepted" |
| lower `a_cut` | more GRIND/CONSOLIDATION (fat POC) |
| bigger `n_rows` | finer profile; small shifts in POC / acceptance |
| bigger `min_bars` | more early windows read UNCLEAR (waits for evidence) |

### `consolidation` — the L2 base detector (leg-based, fractal)

```yaml
strategy:
  consolidation:
    swing_frac: 0.20
    base_method: grade_state    # grade_state | va_frac
    va_thr: 0.55
    min_leg_len: 5
    max_age: 40
```

Finds the 1-minute **consolidation base** whose value-area edges (VAH/VAL) become the
breakout levels the decider trades — the **fractal** way, the same anchor+measurement
pattern as L1:

> **L1** (`structure`) grades the **session** (the clock-given container). **L2** (here)
> grades each **leg** *within* the session (the structure-detected container). Same
> `grade()`, one scale down. A leg with a fat POC / narrow value area is a RANGE = a
> consolidation base. (This replaced an older rolling-window run-detector that wasn't
> leg-based — it's why this section's knobs changed shape.)

A **leg** is a swing (a threshold zigzag): price runs, then only reverses once it retraces
by `swing_frac × the session's range`. Tying the threshold to the session range is what
makes the same `swing_frac` carve legs correctly in a wide day and a tight day
(scale-invariant) — see `experiments/engine/legs.py`.

- **`swing_frac: 0.20`** — leg size. The zigzag reversal threshold as a fraction of the
  session range. *Bigger* → fewer, larger legs (coarser structure); *smaller* → more, finer
  legs. (On NQ: 0.10 ≈ 90 legs/window, 0.20 ≈ 14, 0.40 ≈ 4.) The single most important base knob.
  **Shared:** the **Session Structure** indicator/reading (`src/indicators/session_structure.py`,
  `Snapshot.session_structure`, the chart's *Session Structure* overlay, the monitor's `SESS H/L` box)
  reuses this same threshold to find each session's swing (BOS) high/low on the 5m session — one
  scale-invariant swing definition everywhere. Nudging `swing_frac` moves *both* the L2 base legs and
  the session swing levels.
- **`base_method: grade_state`** — **how a leg is judged a base. Swap this to A/B two definitions:**
  - **`grade_state`** — a base iff `grade(leg).state == CONSOLIDATION`. Reuses the `regime`
    cutoffs above (`e_cut`/`a_cut`), so there is **one** definition of "consolidation" at every
    scale. Stricter: also requires low efficiency (genuinely choppy, not just concentrated).
  - **`va_frac`** — a base iff the leg's value-area fraction `< va_thr`. The archived
    `leg_profiles` rule: value concentration only, ignores efficiency. Looser → many more bases.
- **`va_thr: 0.55`** — *(only used when `base_method: va_frac`)* the value-area fraction below
  which a leg counts as a base. Lower = demand a tighter/fatter POC (fewer bases).
- **`min_leg_len: 5`** — ignore legs shorter than this many bars (too small to be a real base).
- **`max_age: 40`** — ignore a base whose leg *ended* more than this many bars ago (stale — the
  breakout window has passed).

> Either method takes the **levels** (VAH/VAL/POC) from `grade(leg)`, so they never disagree
> with the regime engine — only the base *test* differs. The leg grades are cached keyed by the
> `regime` knobs, so editing `regime` **or** `consolidation` recomputes cleanly — never stale.
>
> `grade_state` vs `va_frac` are genuinely different strategies (very different base counts and
> trade frequency) — flip `base_method` and re-check the chart/backtest to compare.

### `decide` — the va_breakout entry rule

```yaml
strategy:
  decide:
    bias_str: 0.3
    target_r: 2.0
```

The `va_breakout` decider (`src/strategy/decide/va_breakout.py`): in a session that is
directional so far, when price breaks the 1m base's value area **in** the session's
direction, propose the trade.

- **`bias_str: 0.3`** — the **bias filter**: the minimum `|L1 strength|` (session `net ÷
  range`, −1..+1) for the session to count as directional enough to trade. Raise it → only
  strongly one-sided sessions qualify (fewer trades); lower it → trades in flatter sessions.
- **`target_r: 2.0`** — the profit target in **R** (multiples of risk). The stop is the
  opposite value-area edge (= 1R by construction), so `2.0` targets twice the risk. Raise for
  a wider target (lower hit rate, bigger winners); lower for the reverse.

---

## `chart` — chart defaults

```yaml
chart:
  symbol: NQ
  timeframe: 5m
  limit: 10000
```

- **`symbol`** — default instrument (`NQ`, `ES`, …) — must have parquets under
  `data/<symbol>/`.
- **`timeframe`** — default timeframe on load (`1m` / `5m` / `15m` / `60m` / `1d`).
- **`limit`** — how many bars are loaded per timeframe (10000 = the last 10k bars).
  Bigger = more history + more compute.

---

## How to add a new knob

1. Add it under the right block in `algo_config.yaml` (with an inline comment).
2. Read it in the matching `src/config.py` accessor (never hardcode a tunable).
3. Document it here.

This mirrors project convention #3 (every knob in config) and #6 (keep docs current).
