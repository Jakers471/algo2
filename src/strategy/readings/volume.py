"""src.strategy.readings.volume — facts from time-based (per-bar) Volume.

Reads the RAW per-bar volume (src.indicators.volume) and derives what the strategy
looks at at the current bar:
  - bar   : this bar's traded volume.
  - up    : this bar's direction (close >= open) — for a bull/bear tint on `bar`.
  - rvol  : relative volume = this bar / average of the last WINDOW bars
            (a spike reads > 1; quiet reads < 1). Instantaneous — one bar.
  - delta : net signed volume over the last WINDOW bars (up-bar volume minus
            down-bar volume) — recent buying vs selling pressure.
  - vexp  : volume expansion = avg(last FAST bars) / avg(last WINDOW bars).
            ~1 = steady; rising = volume ramping up (the 'steady → boom' build).
            Sustained, unlike rvol's single-bar spike.

The volume PROFILE's session-cumulative volume is a DIFFERENT fact and lives in the
volume_profile reading. Facts only — no opinions (that's score's job).
"""
from __future__ import annotations

# Fallback lookbacks, in bars. build_snapshot passes the live values from
# algo_config.yaml (strategy.readings.volume_window / volume_fast); these default.
WINDOW = 20   # baseline / slow avg (rvol, delta, vexp's denominator)
FAST = 3      # vexp fast avg (short-term)


def read_volume(vol_raw: dict, window: int = WINDOW, fast: int = FAST) -> dict | None:
    """Raw `compute_volume()` result -> {bar, rvol, delta, vexp}, or None if no bars."""
    bars = (vol_raw or {}).get("bars", [])
    if not bars:
        return None
    recent = bars[-window:]
    bar = recent[-1]["value"]
    slow_avg = sum(b["value"] for b in recent) / len(recent)
    fast_bars = bars[-fast:]
    fast_avg = sum(b["value"] for b in fast_bars) / len(fast_bars)
    return {
        "bar": bar,
        "up": bool(recent[-1]["up"]),
        "rvol": (bar / slow_avg) if slow_avg > 0 else 0.0,
        "delta": sum(b["value"] if b["up"] else -b["value"] for b in recent),
        "vexp": (fast_avg / slow_avg) if slow_avg > 0 else 0.0,
    }
