# NOTES

Running log of vision, decisions, and what we learned. Newest first. Entries are
dated + timed and terse (≤50 lines). Split into `notes/` when this gets large.

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
