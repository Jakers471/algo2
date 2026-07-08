"""src.strategy.readings.consolidation — the tradeable L2 base (a fact), leg-based.

The VA-breakout strategy enters on the break of a 1m CONSOLIDATION's value area. This
finds that base the FRACTAL way — the same anchor+measurement pattern used at L1:

  L1 (structure.py): grade() the SESSION (the clock-given anchor).
  L2 (here):         grade() each LEG within the session (the structure-detected anchor).

A LEG is a swing (legs.swing_legs, a threshold zigzag); the threshold = swing_frac * the
session's price range, so the same swing_frac carves legs at any scale (scale-invariant).
Each completed leg is grade()d — a leg with a fat POC / narrow value area is a RANGE =
a consolidation base. The most recent such base's value-area edges (VAH/VAL) are the
breakout levels the decider trades. This restores the archived layer2/leg_profiles design;
the old rolling-window run-detector (mirroring backtest_equity `collect()`) is retired.

Whether a leg counts as a base is SELECTABLE in config (strategy.consolidation.base_method):
  - grade_state : leg is a base iff grade(leg).state == 'CONSOLIDATION' (reuses the regime
                  cutoffs e_cut/a_cut — ONE regime definition at every scale; stricter, also
                  needs low efficiency).
  - va_frac     : leg is a base iff grade(leg).va_frac < va_thr (the archived leg_profiles
                  rule — value-area concentration only, a separate threshold).
Either way the LEVELS (vah/val/poc) come from grade(leg), so they never disagree with the
regime engine. Facts only — whether to TRADE the break is the decider's opinion.
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_REPO, "experiments", "engine"))
from grade import grade  # noqa: E402
from legs import swing_legs  # noqa: E402

# Fallback defaults; the live values come from algo_config.yaml (strategy.consolidation),
# resolved in build_snapshot and passed to read_consolidation.
SWING_FRAC = 0.20    # zigzag reversal threshold as a fraction of the session's range
BASE_METHOD = "grade_state"  # grade_state | va_frac — how a leg is judged a base
VA_THR = 0.55        # (va_frac method) value-area fraction below which a leg is a base
MIN_LEG_LEN = 5      # ignore legs shorter than this many bars (too small to be a base)
MAX_AGE = 40         # ignore a base that ended > this many bars ago (gone stale)

# PERF: grade(leg) is deterministic for a fixed (bars + regime knobs), so we memoize it by
# (grade_sig, leg-start-ts, leg-end-ts). grade_sig makes the cache INVALIDATE the instant a
# regime knob changes (change config -> different reading, never stale). Bounded by
# clear_state_cache() (the runner clears per session; the server on rebuild).
_LEG_CACHE: dict = {}


def clear_state_cache() -> None:
    """Clear the memoized leg grades. Kept under this name so existing callers
    (chart/server.py, the runner) that clear the cache on rebuild keep working."""
    _LEG_CACHE.clear()


def _grade_sig(grade_cfg) -> tuple:
    """Hashable fingerprint of the regime knobs — part of the cache key so a knob
    change misses every stale entry (the values grade() actually depends on)."""
    g = grade_cfg or {}
    return (g.get("n_rows"), g.get("e_cut"), g.get("a_cut"), g.get("min_bars"))


def _leg_grade(window, i0, i1, sig, grade_cfg):
    """grade(window[i0:i1+1]), memoized by (regime knobs, leg-start-ts, leg-end-ts)."""
    idx = window.index
    key = (sig, idx[i0].value, idx[i1].value)
    g = _LEG_CACHE.get(key)
    if g is None:
        g = grade(window.iloc[i0:i1 + 1], **(grade_cfg or {}))
        _LEG_CACHE[key] = g
    return g


def read_consolidation(window, cfg: dict | None = None,
                       grade_cfg: dict | None = None) -> dict | None:
    """Session 1m bars -> the most recent tradeable CONSOLIDATION base, or None.

    `window` = the current session's 1m bars up to `asof` (the L1 container, sliced by
    build_snapshot). `{vah, val, poc, len, ended_ago}` — the value-area edges are the
    breakout levels; `ended_ago` = bars since the base leg completed.

    `cfg` = the resolved consolidation knobs (strategy.consolidation: swing_frac/
    base_method/va_thr/min_leg_len/max_age); `grade_cfg` = the regime knobs for grade().
    Both None fall back to this module's defaults (identical values)."""
    cfg = cfg or {}
    swing_frac = float(cfg.get("swing_frac", SWING_FRAC))
    base_method = str(cfg.get("base_method", BASE_METHOD))
    va_thr = float(cfg.get("va_thr", VA_THR))
    min_leg_len = int(cfg.get("min_leg_len", MIN_LEG_LEN))
    max_age = int(cfg.get("max_age", MAX_AGE))
    min_bars = int((grade_cfg or {}).get("min_bars", 8))

    if window is None or len(window) < min_bars + min_leg_len:
        return None
    hi = float(window["high"].max())
    lo = float(window["low"].min())
    rng = hi - lo
    if rng <= 0:
        return None
    thr = swing_frac * rng
    legs = swing_legs(window, thr)
    if len(legs) < 2:                       # need at least one COMPLETED leg
        return None

    sig = _grade_sig(grade_cfg)
    n = len(window)
    # Scan COMPLETED legs newest-first (exclude the last = the forming leg) for a base.
    for i0, i1 in reversed(legs[:-1]):
        if (i1 - i0 + 1) < min_leg_len:
            continue
        ended_ago = n - 1 - i1
        if ended_ago > max_age:             # legs only get older going back -> stop
            break
        g = _leg_grade(window, i0, i1, sig, grade_cfg)
        if g.vah <= g.val:
            continue
        is_base = (g.state == "CONSOLIDATION") if base_method == "grade_state" else (g.va_frac < va_thr)
        if not is_base:
            continue
        idx = window.index
        return {"vah": g.vah, "val": g.val, "poc": g.poc,
                "len": i1 - i0 + 1, "ended_ago": ended_ago,
                # absolute span (Unix seconds, UTC) so consumers can draw the base box.
                "start": int(idx[i0].value // 1_000_000_000),
                "end": int(idx[i1].value // 1_000_000_000)}
    return None
