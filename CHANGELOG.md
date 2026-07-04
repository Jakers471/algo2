# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Dates are `YYYY-MM-DD`.

## [Unreleased]

### Added
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

### Changed
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
