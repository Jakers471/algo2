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

**Every knob added to `algo_config.yaml` MUST be documented thoroughly in
`algo_config.README.md`** (the in-depth config guide) — what it does, what changing
it affects (with a tuning cheat-sheet where useful), and where it's read — not just
the short inline YAML comment. If one knob feeds several outputs, say so explicitly.
Treat this as part of adding the knob, not an afterthought.

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

### 7. The strategy pipeline — one direction, swappable stages

Turning indicators into trades flows in ONE direction; each stage does a single
job and talks to the next ONLY through a stable contract (never reaching into the
previous stage's internals). Lives in `src/strategy/`:

Tier map — each folder IS a tier; the tree mirrors the flow top-to-bottom
(✅ live · 🟡 seam-only stub · ⬜ not built yet):

```
 bars ─► src/indicators/*            raw math (POC, MA, volume) — also feed chart   ✅ 1
      ─► src/strategy/
           readings/                 raw indicators → FACTS ("price +38 above POC") ✅ 2
           snapshot.py               assemble readings → ONE Snapshot = CONTRACT     ✅ 3
           score/   (base + v1)      facts → weighted signals + conviction. OPINIONS 🟡 4
           decide/  (base + v1)      scores → trade Intent (dir/entry/stop/target)   🟡 5
           manage/  (base+fixed+trailing)  intent → Actions (arm/activate/exit)      🟡 6
           pipeline.py               reads config, wires chosen versions, runs it     ✅ 7
      ─► src/brokers/base.py + adapters   execution translates Actions → Broker      ⬜ 8

 Consumers (read the Snapshot, never raw indicators):
   chart/server.py  /api/replay/state → build_snapshot   |   tools/replay_monitor.py
   src/backtest/    (future: replay loop + simulated Broker adapter)
```

The Snapshot (tier 3) is what the replay monitor AND the strategy consume; nothing
downstream ever touches raw indicators. The swappable stages (score/decide/manage)
are FOLDERS: `base.py` = the seam (interface + registry), version modules beside it
(`v1.py`, `fixed.py`, …) self-register; the active one is chosen in config.

Rules:
- **readings = facts, score = opinions.** Keep them apart so you can rewrite how
  you judge without changing what you measure (and vice-versa).
- **Contracts are stable.** Adding a Snapshot field is additive and safe (old
  consumers ignore it); renaming/removing is the only breaking change.
- **Stages are swappable per stage.** score/decide/manage each register named
  versions (like the JS indicator registry); the active one is chosen per stage in
  `algo_config.yaml` under `strategy.use` (`scorer`/`decider`/`manager`). Swap a
  stage = change one word; nothing else moves. A "strategy" = a named combo of
  versions.
- **Same stream everywhere.** live/replay/backtest all consume the identical
  Snapshot stream, so they can't diverge. The replay monitor is just one consumer.
- **Broker-agnostic** (see #4): the pipeline never touches broker-specific code.

Adding an indicator to the pipeline — ASK these, in order, before coding:
1. Which indicator? (its raw math)  2. What number(s) will it derive? (the
reading/fact)  3. How do you want to read those numbers? (monitor/state form)
4. (later) Does it feed scoring, and how much? Then: add a `readings/` module +
a Snapshot field — the snapshot auto-combines it, no other wiring.

### 8. Extending these conventions

Add new numbered conventions here as the project's needs grow.
