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

## `strategy` — the pipeline (versions + reading knobs)

```yaml
strategy:
  use:
    scorer:  v1
    decider: v1
    manager: fixed
  readings:
    volume_window: 20
    volume_fast: 3
```

Mirrors `src/strategy/` (`readings → snapshot → score → decide → manage`). See
`src/strategy/README.md` for the full pipeline.

### `use` — which VERSION of each swappable stage runs

Each stage (`scorer` / `decider` / `manager`) is a folder of interchangeable
versions. These three lines pick which one is active. **Swap a stage by changing
one word** — e.g. `manager: fixed → trailing` — and nothing else moves. A
"strategy" is just a named combo of versions. (score/decide/manage are stubs today,
so these don't do anything visible yet — the wiring is in place for when they do.)

### `readings` — how the SNAPSHOT facts are derived

Knobs for turning raw indicator output into the facts in the Snapshot. Right now,
these are the **volume** lookback windows.

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
