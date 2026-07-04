# volume_profile_algo

## Conventions

### 1. Organization & structure (modular)

Keep everything modular. Group code by concern into clearly-labeled,
self-contained folders — each folder owns one thing and holds all files
related to it.

Top-level layout:
- **`src/`** — the backend (Python), the "brain": `indicators/` (pure math),
  `strategy/` (decisions), `brokers/` (abstraction + adapters), `backtest/`.
- **`chart/`** — the frontend (reusable UI): a thin view that renders whatever
  the backend computes. `chart/server.py` is the seam (serves the page + API,
  importing from `src/`).
- **`data/`** — datasets + pipeline (parquets gitignored).

### 2. Backend/frontend split — one source of truth for math

Anything numeric (indicator values, signals, decisions) lives in **`src/`** and
is computed **once**. The chart and the backtester both consume the same
functions so they can't drift. The frontend never reimplements math — it fetches
computed values from the API and draws them. Presentation (styling, show/hide)
is the frontend's job; windows/parameters/logic are the backend's.

### 3. Config — every knob in `algo_config.yaml`

Every tunable parameter/knob lives in **`algo_config.yaml`** (session windows +
colors, volume-profile `row_size`/`value_area_pct`, chart defaults). `src/config.py`
reads it **live** (per request — edit + refresh, no restart). Backend defaults,
the chart, and (soon) the strategy + backtester all resolve knobs through it, so
what you see on the chart is exactly what a backtest/strategy would run on. The
frontend fetches it from `/api/config`; even colors are config-driven. Add a new
knob here first, then read it via `src/config.py` — never hardcode a tunable.

### 4. Architecture — strategy decoupled from broker

The trading strategy MUST stay independent of broker-specific code. A **broker
abstraction layer** defines one standard interface (a fixed set of methods) that
the strategy calls; per-broker **adapters** translate those calls to each
broker's API. Adding or swapping a broker must never require touching strategy
logic. Do not let broker-specific details leak into the strategy backend.

### 5. Indicators — two halves: math (backend) + renderer (frontend)

Each indicator has two self-contained modules:
- **Math** in `src/indicators/<name>.py` — pure: OHLCV in, values/levels out. No
  UI, no I/O, no strategy/broker knowledge. This is the single source of truth
  (chart + backtest use it). The server exposes it at `/api/indicators/<name>`.
- **Renderer** in `chart/static/js/indicators/<name>.js` — fetches the computed
  values and draws them; a pluggable, toggleable chart module (master + optional
  per-item toggles via the control panel). Never computes the math itself.

An indicator never depends on another indicator or on strategy internals. Add
one by dropping in the two modules, not by editing existing ones.

### 6. Documentation & records — keep these current

Update these whenever you make a change; treat it as part of the task, not an
afterthought.

- **`CHANGELOG.md`** — append every meaningful change (loosely Keep a Changelog
  style, dated `YYYY-MM-DD`). New work goes under `[Unreleased]`.
- **`NOTES.md`** — running log of conversations, vision, decisions, and what we
  learned. Each entry is dated **and timed**, structured, and to the point —
  aim for ≤50 lines per entry, less if possible, but capture the *why*. Newest
  first. When it gets large, split into a `notes/` folder (versioned).
- **`requirements.txt`** — the single source of truth for dependencies. Any new
  dependency is added here immediately, with a version floor and a short
  inline comment on what it's for. Remove entries that are no longer used.

### 7. Extending these conventions

Add new numbered conventions here as the project's needs grow.
