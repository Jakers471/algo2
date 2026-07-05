# Archived experiment — micro_zones (VAH/VAL-anchored micro consolidations)

**Status:** shelved 2026-07-05. Not wired into the app. Kept for reference.

## What it did
One profile **per timeframe**, self-contained:
- **Base** = that timeframe's session volume-profile value area (VAH/VAL) — *read*, not detected.
- **Micro** = tight-range runs of `min_bars`..`max_bars` (default 30–80) bars on the
  same timeframe that stay **inside** the VAH/VAL channel (band ≤ `tightness` × channel).

Knobs (function defaults, were URL-overridable): `tightness=0.40`, `min_bars=30`,
`max_bars=80`. Nothing ever added to `algo_config.yaml`.

## Why it's shelved
See NOTES.md (2026-07-05). Short version: the micro layer is a **price-action**
construct (tight-range run) bolted onto a **volume** construct (value area) — they
don't share a basis, so the zones don't correspond to volume structure; the
"every bar inside VAH/VAL" rule is brittle to wicks; and the single-timeframe
version dropped the LTF-in-MTF-in-HTF nesting that motivated the idea.

## To re-enable
1. `micro_zones.py` → `src/indicators/`
2. `micro_zones.js` → `chart/static/js/indicators/`
3. `chart/server.py`: add `from src.indicators.micro_zones import compute_micro_zones`
   and a `/api/indicators/micro_zones` route (see git history / the reverted diff).
4. `chart/chart.html`: add `<script src="./static/js/indicators/micro_zones.js">`.
