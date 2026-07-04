# volume_profile_algo

## Conventions

### 1. Organization & structure (modular)

Keep everything modular. Group code by concern into clearly-labeled,
self-contained folders — each folder owns one thing and holds all files
related to it.

### 2. Architecture — strategy decoupled from broker

The trading strategy MUST stay independent of broker-specific code. A **broker
abstraction layer** defines one standard interface (a fixed set of methods) that
the strategy calls; per-broker **adapters** translate those calls to each
broker's API. Adding or swapping a broker must never require touching strategy
logic. Do not let broker-specific details leak into the strategy backend.

### 3. Indicators — pluggable, toggleable chart modules

Each indicator (volume profile, etc.) is a **self-contained module** that
attaches to the chart and can be turned **on/off individually** at runtime.
- One indicator per module, under the chart layer (e.g.
  `chart/indicators/<name>`), exposing a standard attach/detach (enable/disable)
  interface the chart calls.
- An indicator never depends on another indicator or on strategy internals — it
  takes data in and draws on the chart. Add an indicator by dropping in a new
  module, not by editing existing ones.

### 4. Documentation & records — keep these current

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

### 5. Extending these conventions

Add new numbered conventions here as the project's needs grow.
