# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Dates are `YYYY-MM-DD`.

## [Unreleased]

### Added
- Indicator framework: pluggable module registry
  (`chart/static/js/indicators/registry.js`) + a toggle bar in the chart header;
  indicators self-register and can be turned on/off individually at runtime.
- **Sessions H/L** indicator (`chart/static/js/indicators/sessions.js`): draws
  dashed, color-coded rays from each Asia/London/NY session's high and low,
  extending right until a later candle tests the level. Session windows anchored
  to America/Chicago (DST-aware); on by default; skipped on the 1d timeframe.
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
- Chart time axis and crosshair now use 12-hour format; removed the chart grid.
- Moved the chart frontend under `chart/` so the UI stays self-contained and
  reusable across tasks.
