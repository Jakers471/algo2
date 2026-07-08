# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Dates are `YYYY-MM-DD`.

## [Unreleased]

### Fixed
- **QC LEAN — hard EOD flatten (multi-day-hold leak).** The session-flatten only runs when a 5m
  bar arrives, so a position open into a weekend/data-gap could ride for days (up to 89h / 3.7
  days observed; 13% of the 2015-2026 trades were held >12h). Added a scheduled `FlattenEod` at
  15:55 CT every day (data-independent, before the 16:00 CT CME daily halt) so the strategy is
  genuinely intraday — no overnight/weekend gap exposure. The local sim was already strict here.
- **QC LEAN execution — real bracket orders (the "0% win" bug).** The QC port's manual
  `CheckExit` read the 1m bar's aggregate high/low and couldn't tell whether the stop was hit
  *before or after* the entry filled within the same bar; with a tight consolidation VA that
  stopped nearly every trade out at −1R (2015–2026 run: **0% win, −545R**, and only 4/1041 long
  fills). Replaced it: once the entry stop fills, `Main.cs` now places a **real stop-market +
  limit bracket** (manual OCO in `OnOrderEvent`), and rollover/session-close go through
  `FlattenPosition`. Child orders only trigger on *later* bars, so the entry's own bar can't stop
  it out. Strategy math untouched (csverify stays green; NT/Python unaffected).
- **QC LEAN price-scale mismatch (the "all-short / 4-long" bug).** `Main.cs` computed order prices
  (Vah/Val) from **BackwardsRatio-adjusted** continuous data but submitted them on the **raw**
  `_future.Mapped` contract. The adjustment grows back in time (anchored at the present), so pre-2026
  buy-stops landed far *above* the raw market (never filled — 4/1041 longs) while sell-stops
  triggered *instantly* at garbage prices (582 shorts, all losers). Fingerprint: the algo's R
  (adjusted levels) read ~0 while QC's P&L (raw fills) was −$53k. Fix: switch to
  `DataNormalizationMode.Raw` so signal prices and order prices share one scale; break the session
  on `SymbolChanged` (clear 1m + 5m buffers) so a raw roll-jump can't span a grade window. Intraday
  signals are unchanged within a session (Raw ≡ BackwardsRatio in shape); math untouched.

### Added
- **`backtests/` — one home + one analytics engine for every backtest run.** Each
  run (NinjaTrader, QuantConnect, or Python) lands in `backtests/runs/<run_id>/`
  as a self-describing folder: raw `trades.csv`/`trades.json` + a `meta.json` label
  (platform, bar type, tick-replay, commission/slippage, fill resolution, params
  snapshot, sample type). `analyze.py` normalizes any engine's dump to one canonical
  trade schema and writes `report.md` + `equity.png` (stats in the same vocabulary as
  `src/backtest/report.py`: win%, expectancy R, total R, maxDD, profit factor, net $,
  target-hit%), appending a row to `registry.csv`. `compare.py` puts N runs side by
  side and flags when their cost/fill contracts don't match. `import_qc.py` pulls a
  QC ObjectStore trades JSON into a labeled run. See `backtests/README.md`.
- **csverify third target (NinjaTrader).** `tools/csverify` now verifies NT's
  List-based `Grade`/`FindConsolidation` (`ninjatrader/VABreakout.cs`) against the
  Python source of truth alongside the LEAN Span version — so all three impls are
  proven signal-identical (Python == LEAN == NT, 52/52 consolidation + grade).
- **NinjaTrader run capture + AI brief.** `ninjatrader/NT_AI_BRIEF.md` is the contract
  for the NT8 assistant (frozen constants, required config, cost/fill contract, export
  format, gotchas, stay-aligned workflow). NT export upgraded (`TradeExporter.cs`):
  per-trade Stop/Target/R, a Minute/1 fail-fast guard, and auto-save into
  `backtests/runs/` with `meta.json`.
- **Top-level `README.md` front door** — replaced the 3-line stub with a proper
  "start here" for humans and AIs: the strategy in three sentences, an ordered
  reading path (CLAUDE.md → GRADE_SPEC → src/strategy in flow order → validation →
  NOTES), a repo map, run commands, and an **honest-status note** on the
  fill-mirage (paper ~55–62% win vs QC-real 43% market / 14% stop; min-VA-width
  filter flagged as the open fix).
- **ATR indicator (experimental)** — Average True Range wired in as a normal
  indicator (both halves, CLAUDE.md #5). Math: `src/indicators/atr.py` (Wilder
  smoothing of true range, per-bar values in points; drops `period-1` warm-up bars
  like the MAs) served at `/api/indicators/atr`. Renderer:
  `chart/static/js/indicators/atr.js` — a line docked in a lower band of the price
  pane (v4 has no true sub-panes, so it shares the band with volume, same overlay
  trick as `volume.js`), toggled from the panel, **off by default**. Config: new
  `atr` block (`period`/`color`/`height_pct`) in `algo_config.yaml`, resolved by
  `src.config.atr_config()`, documented in `algo_config.README.md`.
- **Volume reading in the Snapshot** — `src/strategy/readings/volume.py` derives
  four facts from the time-based volume indicator at the current bar: `bar`
  (this bar's volume), `rvol` (relative volume vs the last 20 bars — a spike reads
  >1), `delta` (net signed volume over the last 20 bars — buying vs selling), and
  `vexp` (volume expansion = avg(fast bars) / avg(window bars) — ~1 steady, rising
  = ramping up; catches "steady → boom" that rvol's single-bar spike misses). Added
  as a `volume` field on the Snapshot; shown in the monitor's SNAPSHOT bucket beside
  the profile's session-cumulative `vol`. Lookbacks are config knobs
  (`strategy.readings.volume_window` = 20, `volume_fast` = 3), resolved in
  `build_snapshot` and passed to the reading (readings stay pure). Monitor gains
  `--legend` (a guide to what every field means).
- **Replay monitor: two pipeline views** (`tools/replay_monitor.py --view`):
  `horizontal` (default) a bucketed grid — one boxed column-group per phase
  (SNAPSHOT/SCORE/DECIDE/MANAGE), one row per bar; `vertical` a funnel block per
  bar; `snapshot` the facts-only table. Consistent phase palette across views
  (SNAPSHOT=cyan · SCORE=yellow · DECIDE=magenta · MANAGE=blue), semantic value
  colors, ANSI-on-Windows, `--no-color`. `/api/replay/state` now returns the full
  `pipeline.run()` result (`snapshot, scores, intent, action`) instead of just the
  snapshot; SCORE/DECIDE/MANAGE cells show `—` until those stub phases get logic —
  the layout lights up automatically as each phase returns data. Build roadmap in
  `src/strategy/README.md`.
- **Strategy pipeline scaffold** (`src/strategy/`, CLAUDE.md #7): one-directional
  `indicators → readings → snapshot → score → decide → manage → pipeline`, each
  stage talking only through stable contracts. Live now: `readings/volume_profile.py`
  (raw VP → forming-session facts) + `snapshot.py` (`build_snapshot` → the Snapshot
  contract carrying `price` + the volume-profile reading). Seam-only stubs (no
  logic yet) as stage FOLDERS mirroring the tiers: `score/`, `decide/`, `manage/`,
  each `base.py` (interface + name→version registry) + version modules (scorer
  `v1`, decider `v1`, manager `fixed`/`trailing`) that self-register;
  `pipeline.py` wires the config-chosen versions. New `strategy.use` block in
  `algo_config.yaml` (per-stage version selectors) via `strategy_config()`.
- The **replay monitor now reads the true Snapshot**: `/api/replay/state` builds
  it with `build_snapshot` (the same object the strategy will consume) instead of
  an ad-hoc volume-profile calc; `tools/replay_monitor.py` reads `snapshot.*`.
- **Volume** indicator (time-based) — extracted the per-bar volume histogram out
  of the chart core into a proper pluggable indicator, matching convention #5.
  Math in `src/indicators/volume.py` (pure: OHLCV in, per-bar `{time, value, up}`
  out — the single source of truth for chart + backtest), served at
  `/api/indicators/volume`, rendered by
  `chart/static/js/indicators/volume.js` as a bottom-band histogram series with a
  master toggle (on by default); recomputes as-of each replay frame like the
  other indicators. Bar colors + band `height_pct` are config knobs under
  `volume` in `algo_config.yaml` (`volume_config()` in `src/config.py`).

### Changed
- `chart/static/js/chart.js` no longer builds the volume series inline: it hosts
  candles only and lets the `volume` indicator draw the histogram. `createChart`
  returns `{chart, candleSeries}`, `render(candleSeries, data)` drops the volume
  arg, and sample-data mode is candles-only (volume is API-driven now).

- **Replay terminal monitor** — a standalone reader for the replay readout.
  `tools/replay_monitor.py` polls the server and streams the forming session's
  `when · session · POC · VAH · VAL · vol` into a separate terminal, printing
  `replay initialised` / `replay ended` on the transitions. The chart
  fire-and-forgets its replay cursor to a new in-memory endpoint
  (`POST/GET /api/replay/state`) via `navigator.sendBeacon` — never awaited, so
  it adds zero latency to the replay loop; the server computes the readout lazily
  on poll (reusing `compute_volume_profile`, cached per-`asof`), off the browser.
- **Dev server no-cache**: `chart/server.py` now sends `Cache-Control: no-store`
  on every response so a plain browser refresh always loads the latest
  chart/JS/CSS/config (no hard-refresh needed).
- **Moving Averages** indicator — `src/indicators/moving_average.py`: SMA or EMA
  (per-line `type`) of a configurable price `source` (close by default), one line
  per `period` (20 / 50 / 200, SMA by default). Pure math (single source of truth
  for chart + backtest), served at `/api/indicators/moving_average`, and rendered
  as Lightweight-Charts line series
  (`chart/static/js/indicators/moving_average.js`) with per-line toggles.
  Type/periods/colors/source are config knobs under `moving_averages` in
  `algo_config.yaml`; recomputes as-of each replay frame.

- **`algo_config.yaml`** — single source of truth for every tunable knob
  (session windows + colors, volume-profile `row_size`/`value_area_pct`, chart
  defaults). `src/config.py` reads it live (edit + refresh, no restart). Backend
  defaults, endpoints, and the chart all resolve knobs through it; `/api/config`
  serves it to the frontend, which drives colors/params (even session colors)
  from it. Will also drive the strategy + backtester.
- **`src/` backend** (the "brain"): `indicators/` (pure math), plus `strategy/`,
  `brokers/` (with a `Broker` interface skeleton), and `backtest/` placeholders.
- `src/indicators/sessions.py` — session H/L math (OHLCV → rays + verticals),
  now the single source of truth for the chart *and* future backtests. Exposes a
  shared `session_instances()` so indicators reuse one session grouping.
- **Volume Profile** — `src/indicators/volume_profile.py`: per-session volume
  profile with overlap-weighted volume distribution, POC, and value area
  (VAL/VAH). `bins` and `value_area_pct` are computation parameters (not display
  filters), so the chart and strategy get identical numbers. Served at
  `/api/indicators/volume_profile`; rendered as a sideways histogram
  (`chart/static/js/indicators/volume_profile.js`) with shaded value area, a
  highlighted POC + POC line, and per-session toggles. Off by default.
- `/api/indicators/sessions` endpoint serving the computed levels.
- Indicator framework: pluggable module registry
  (`chart/static/js/indicators/registry.js`) + a floating control panel on the
  chart's upper-left; indicators self-register with an optional master toggle and
  per-item sub-toggles (with color swatches).
- **Sessions H/L** indicator (`chart/static/js/indicators/sessions.js`): draws
  dashed, color-coded rays from each Asia/London/NY session's high and low,
  extending right until a later candle tests the level, plus dashed vertical
  session start/end lines (canvas series primitive) in the same color. Each
  session toggles independently. Windows anchored to America/Chicago (DST-aware);
  on by default; skipped on the 1d timeframe.
- Documentation scaffolding: `CHANGELOG.md`, `NOTES.md`, and CLAUDE.md
  policies for keeping the changelog, notes, and `requirements.txt` current.
- CLAUDE.md conventions: broker-abstraction architecture rule; indicators as
  pluggable, toggleable chart modules.
- `chart/server.py` — Flask backend serving the chart + a JSON API
  (`/api/timeframes`, `/api/candles`) that reads the NQ parquets and returns the
  last 10,000 bars per timeframe (Unix-second UTC times), lru-cached.
- Timeframe selector (1m/5m/15m/60m/1d) in the chart header, wired to live NQ
  data with a bar-count status line.
- `chart/` frontend (TradingView Lightweight Charts, dark theme): candlesticks
  + volume histogram.
- `data/` pipeline (`build_data.py`) and clean NQ/ES parquets (gitignored).
- `.gitignore` excluding the large parquet data files.

### Added
- **Replay tool:** step bars forward from any point at 1x/2x/4x while the volume
  profile / POC / VAH / VAL and session levels recompute as-of each bar, with a
  live log line (`session · POC/VAH/VAL · vol`). Backend gains an `asof` param
  (compute on bars `<= asof` — the same math on a growing slice); frontend adds
  `replay.js` (Play/Pause, speed, step, scrubber) wired to a `replay` button.
  Enter starts from the left of the current view; exit restores the live chart.
- **Click a session -> its levels on the chart:** clicking a session's time span
  overlays that session's H / VAH / POC / VAL / L as labeled lines (from the
  config's `row_size`/`value_area_pct`), with a faint span + value-area shade.
  Click again or on empty space to clear. One canvas primitive, no popup, no
  extra series (`chart/static/js/session_detail.js`). The selection **persists
  through replay** — the levels stay drawn and update live as-of each bar
  (cleared only on a timeframe change).
- **View state persists across refresh:** the chart saves the timeframe, the
  visible time range (zoom + position), and indicator toggles (per-session too)
  to `localStorage` and restores them on load, instead of resetting to
  `fitContent`. Timeframe switches now also keep the same time window.

### Changed
- **Performance:** session H/L rays now render as a single canvas primitive
  instead of ~120 individual Lightweight-Charts line series. Pan/zoom and panel
  toggles are dramatically smoother (toggling is now a repaint, not a
  teardown/rebuild of many series).
- **Chart palette** refreshed to a darker/warmer theme (background `#0d0d0d`/
  `#1a1a19`, text `#c3c2b7`, up `#199e70`, down `#e66767`, accent `#3987e5`).
- **Volume profile now uses a fixed `row_size`** (price per row) on an absolute
  price grid instead of a fixed bin count — so every row is the same height and
  rows line up across sessions (fixes uneven-looking bins). `row_size` is a
  config knob.
- Indicators + server default their parameters from `algo_config.yaml` rather
  than hardcoded values; session windows/tz/cap now come from config too.
- **Backend/frontend split:** session H/L math moved from JavaScript to
  `src/indicators/sessions.py`. The JS sessions module is now a thin renderer
  that fetches computed levels from the API and draws them (colors stay
  frontend). CLAUDE.md updated with the split + one-source-of-truth conventions.
- Chart time axis and crosshair now use 12-hour format; removed the chart grid.
- Moved the chart frontend under `chart/` so the UI stays self-contained and
  reusable across tasks.
