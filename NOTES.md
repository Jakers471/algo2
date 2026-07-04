# NOTES

Running log of vision, decisions, and what we learned. Newest first. Entries are
dated + timed and terse (≤50 lines). Split into `notes/` when this gets large.

---

## 2026-07-03 20:40 CDT — Persist chart view across refresh

**Jake:** refresh reset the chart to default layout; wanted the exact window
(same zoom + position) + selections restored on reload.

**Done (frontend only):** save `{symbol, tf, visible range, indicator states}` to
`localStorage` (`vpa.viewstate.v1`) on pan/zoom (debounced) + on any toggle, and
restore on load. Removed `fitContent()` from render — `select()` now restores the
saved window on first load, keeps the current window across a timeframe switch,
and only fits when there's nothing saved. Guarded by symbol (won't restore a
different instrument's view). Uses LWC `getVisibleRange`/`setVisibleRange`/
`subscribeVisibleTimeRangeChange` (confirmed in the v4.2 bundle).

**Verified:** indicator state roundtrip (toggle → getState → rebuild from it) is
an exact match; page/assets serve. Range restore relies on the LWC APIs above.

---

## 2026-07-03 20:32 CDT — Perf: rays → canvas primitive; new palette

**Jake compared to a reference chart** (…/algo/algoproj/simplicity, port 8765) —
liked its colors + felt it was snappier/smoother, including the indicator modal.
Read its files directly: it draws overlays as SVG (addLineSeries count = 1).

**Root cause found:** our sessions H/L drew **~120 individual LWC line series**
(60 sessions × high+low). LWC re-projects every series each frame → laggy
pan/zoom; and each panel toggle **tore down + rebuilt** all series → laggy modal.

**Fix:** rewrote `sessions.js` so rays + verticals are ONE canvas primitive
(same technique as the vertical lines / volume profile). Verified headlessly:
**0 addLineSeries calls** (was ~120), 240 canvas strokes, toggling = pure
repaint (no series churn), 1d clears, destroy detaches.

**Palette:** adopted the reference theme — bg #0d0d0d/#1a1a19, text #c3c2b7,
up #199e70, down #e66767, accent #3987e5, borders rgba(255,255,255,.10). Grid
already off.

**Still TODO / noticed:** reference also draws the volume profile as an SVG
overlay and has a richer sidebar (backtest run panel, per-session stat modules,
chat log). Ours' VP is already a single primitive (fine). Their sidebar hints at
the backtest UI we'll build next.

---

## 2026-07-03 20:24 CDT — algo_config.yaml (all knobs) + uniform bins fix

**`algo_config.yaml`** is now the single source of truth for every knob (session
windows+colors, VP row_size + value_area_pct, chart defaults). `src/config.py`
reads it **live** per request — verified: edited row_size 5.0→2.5, `/api/config`
and the computed profile both changed with **no restart**. Backend defaults,
endpoints, and the frontend all resolve knobs through it; `/api/config` feeds the
chart (colors, symbol/tf, params). Indicators refactored to read config; session
windows/tz/cap no longer hardcoded. **This config will also drive the strategy +
backtester.**

**Fixed "bins look different sizes" (Jake):** each session was dividing its own
range into a fixed *count* (24), so wide sessions got taller rows. Switched VP to
a fixed **`row_size`** (price per row) on an **absolute price grid** → every row
is the same height and rows line up across sessions. Verified: all rows exactly
row_size tall, edges on grid, volume conserved, VA≥70%.

**Roadmap (Jake set order):** next = **backtesting framework + wiring up the
strategy** (before more chart features). The config + `src/` split were built to
sit under that. brokers/ has a Broker interface stub; strategy/ + backtest/ are
placeholders ready to fill.

**Verified**: /api/config serves knobs; VP uses config row_size (uniform rows);
query override + live YAML edit both work; renderers pull colors from config
(swatches match), draw, toggle, detach.

---

## 2026-07-03 20:13 CDT — Volume Profile indicator + params discussion

**Built per-session Volume Profile** (`src/indicators/volume_profile.py`): for
each session's high→low range, bin the price, distribute each bar's volume
**overlap-weighted** across the rows it spans (conserves total volume — verified),
then derive **POC** and **value area (VAL/VAH)**. Reuses `session_instances()`.
Served at `/api/indicators/volume_profile`; JS renders a sideways histogram
(value area shaded, POC highlighted + line), per-session toggle, off by default.

**Params clarified with Jake (important design call):**
- `bins`/row-size and `value_area_pct` are **computation parameters in the
  backend**, NOT frontend visual filters. Changing bins → recompute (refetch),
  so the chart and strategy always agree. Verified live: POC moved
  21940→21933→21930 as bins went 12→24→48.
- **POC is an OUTPUT** ("the truth"), not a knob — but its value depends on bin
  resolution. **`value_area_pct` (70%) does NOT move POC**; it only sets how wide
  VAL/VAH sit around it. Session H/L = pure facts.
- For strategy: session H/L + POC are computed signals; the 70% gate (→ VAL/VAH)
  is the tunable hyperparameter if entering off the value edges. All come from
  one `compute_volume_profile(df, bins, value_area_pct)` call.

**Verified**: volume conserved, VAL≤POC≤VAH, VA≥70%, one POC row; API 60
profiles; renderer draws 1440 rects + 60 POC lines, toggles, skips 1d, detaches.

---

## 2026-07-03 20:03 CDT — Backend/frontend split (src/) 

**Decision (Jake):** indicator *logic* belongs in Python, not JS — the algo will
backtest + make entry/exit decisions on the same math the chart shows, so it must
live once. Split the repo into **backend (`src/`)** and **frontend (`chart/`)**.

- **`src/`** = the brain: `indicators/` (pure OHLCV→values math), `strategy/`,
  `brokers/` (Broker interface skeleton), `backtest/`. Placeholders for the last
  three; only sessions math is real so far.
- **`src/indicators/sessions.py`** — ported the session H/L math from JS. Pure,
  DataFrame in / rays+verticals out. Verified it produces **identical** results
  to the old JS (48 rays on 2000 5m bars, same prices/times).
- **`chart/server.py`** = the seam: added `/api/indicators/sessions`, imports
  `src/`. The JS sessions module is now a **thin renderer** (fetch + draw).
- **Rule (now in CLAUDE.md):** anything numeric lives in `src/`, computed once;
  frontend only renders. Colors/styling = frontend; windows/params = backend.

**Verified** full pipeline headlessly: Python compute == JS baseline; API returns
120 rays at 10k/5m (cap 60 instances); slimmed renderer draws + toggles + skips
1d + detaches on destroy. Canvas draw still needs a visual eyeball.

**Gotcha:** hit two stale Flask servers bound to :5000 masking the new route —
kill all python before restarting when testing the server.

---

## 2026-07-03 19:51 CDT — Sessions control panel + vertical boundaries

- **Floating control panel** (chart upper-left): per-indicator master toggle +
  per-item sub-toggles with color swatches. Framework generalized: indicators can
  declare `items` and expose `setItemVisible(id, on)`; `create` now receives
  `{ chart, candleSeries }`. Replaces the old header toggle bar.
- **Sessions H/L**: each session (Asia/London/NY) toggles independently; added
  **dashed vertical lines at session start/end**, same color as the session.
- **Vertical lines** use a Lightweight Charts **series primitive** (no native
  vertical line exists) — one canvas pass draws all boundaries via
  `timeToCoordinate` + `useMediaCoordinateSpace`. Verified the API exists in the
  vendored v4.2 build before relying on it.
- **Verified** headlessly on real 5m NQ data: all-on = 48 rays / 48 verticals;
  toggling Asia off drops both to 32; re-enable restores; 1d clears; destroy
  detaches the primitive. (Canvas rendering itself not machine-checkable — needs
  a visual eyeball.)

---

## 2026-07-03 19:43 CDT — Indicator framework + Sessions H/L

**Built the indicator system** (first of the pluggable chart modules):
- `indicators/registry.js` — global registry; each indicator self-registers.
  The chart renders a toggle button per indicator and drives enable/disable +
  data updates. Indicators never reference each other.
- `indicators/sessions.js` — **Sessions H/L**. Per session (Asia/London/NY) per
  day, find high & low; draw a **dashed, color-coded ray** from that point
  extending right until a later candle trades back to the level, then stop.
  Colors: Asia blue, London amber, NY purple. On by default; skipped on 1d.

**Decisions / assumptions:**
- Session hours anchored to **America/Chicago** (exchange tz), DST-aware via
  `Intl`. Using the "Full sessions" preset hours *as Chicago local time*:
  Asia 18:00–03:00, London 03:00–08:00, NY 08:00–17:00. Single config block at
  top of `sessions.js` — easy to retune. (Note: preset was labeled ET; treated
  literally in CT per the tz choice. Flag if you meant ET clock → convert −1h.)
- One line series per ray (LWC can't put overlapping-time levels in one series).
  Capped at the 60 most-recent session instances (`MAX_SESSIONS`) so high TFs
  spanning many days don't spawn thousands of series.

**Verified** headlessly against real 5m NQ data: rays horizontal, dashed,
well-formed; session assignment matches Chicago windows; 1d draws nothing.

**Deferred:** vertical session-boundary markers (earlier idea) — sticking to the
"just show H/L rays" version for now.

---

## 2026-07-03 19:32 CDT — Project vision & scaffolding

**What this is:** an algorithmic trading strategy project. Core = a volume
profile indicator (plus supporting indicators) driving a strategy, with a
reusable chart UI for visualization.

**Architecture decisions:**
- **Broker abstraction layer.** Strategy logic stays fully decoupled from broker
  code. One standard interface the strategy calls; per-broker adapters translate
  to each API. Swapping/adding a broker must not touch the strategy backend.
- **Indicators = pluggable chart modules.** Each indicator is a self-contained
  module that attaches to the chart and can be toggled on/off individually at
  runtime. Add one by dropping in a module, not editing existing code.

**Indicators planned:**
1. **Volume profile** — the core indicator.
2. **Sessions H/L** — maps each session's high→low: Asia, London, NY
   (separately). Toggleable like the rest.
3. A few more TBD.

**Chart UI (this session):**
- Wired the NQ parquets to the chart via `chart/server.py` (Flask). API returns
  the last 10k bars per timeframe; selector for 1m/5m/15m/60m/1d.
- Requested tweaks: horizontal (time) axis in 12-hour format; remove the chart
  grid.

**Docs process (now enforced via CLAUDE.md):** keep `CHANGELOG.md`, `NOTES.md`,
and `requirements.txt` current as part of every change.

**Roadmap (rough order):** broker abstraction layer → volume profile indicator →
sessions H/L indicator → wire strategy on top.
