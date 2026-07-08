"""experiments/engine/grade.py — the ONE measurement. grade(bars) -> Grade.

Per experiments/GRADE_SPEC.md: the full metric set computed on ANY anchor (a run of
OHLCV bars), identically at every scale. No layer computes a subset — that's the
anti-drift rule. Reuses the project's volume-profile math (`_profile_for`,
`_value_area`) so the profile is the same object everywhere.

Pure: an OHLCV DataFrame in, a Grade out.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.indicators.volume_profile import _profile_for, _value_area  # noqa: E402

N_ROWS = 24        # fixed rows per anchor -> va_frac is scale-invariant (comparable across anchors)
E_CUT = 0.38       # efficiency >= this = directional (progress)
A_CUT = 0.55       # acceptance  >= this = accepted (fat POC)
MIN_BARS = 8       # fewer bars than this -> UNCLEAR

# These four are the regime knobs. They are PARAMETERS of grade() (defaults above),
# NOT read from config here — grade() must stay pure OHLCV-in/values-out (it is the
# frozen research core, reused by chart/backtest/research). Callers in src/strategy
# resolve them from algo_config.yaml (strategy.regime) and pass them in, so the engine
# is tunable without the engine ever importing config. See src/config.strategy_config.


@dataclass
class Grade:
    # direction / strength
    direction: str          # "bull" | "bear" | "flat"
    net: float
    range: float
    strength: float         # net / range          (Layer-1 "net %": how far it ended)
    # path
    travel: float
    efficiency: float       # |net| / travel        (progress: how directly it got there)
    swings: int
    # shape
    body_pct: float
    close_pos: float        # 0 = closed on low, 1 = on high
    up_wick: float
    low_wick: float
    # timing
    t_high: float           # 0 start .. 1 end
    t_low: float
    # volume
    vol: float
    delta: float
    # volume profile
    poc: float
    vah: float
    val: float
    va_frac: float
    poc_loc: float          # where value formed, 0..1 of range
    acceptance: float       # 1 - va_frac
    # scale (needs external ATR; None if not supplied)
    scale: float | None
    # regime verdict + collapsed meta-candle (for the recursion)
    state: str
    meta: dict


def _profile(highs, lows, vols, n_rows=N_ROWS):
    lo, hi = float(lows.min()), float(highs.max())
    rng = (hi - lo) or 1e-9
    rs = rng / n_rows
    binvol = _profile_for(highs, lows, vols, range(len(highs)), lo, rs, n_rows)
    if binvol.sum() <= 0:
        return lo, rs, 0, 0, n_rows - 1
    poc = int(binvol.argmax())
    va_lo, va_hi = _value_area(binvol, poc, 0.70)
    return lo, rs, poc, va_lo, va_hi


def _classify(eff, acc, direction, ok, e_cut=E_CUT, a_cut=A_CUT):
    if not ok:
        return "UNCLEAR"
    dirn = "UP" if direction == "bull" else "DN"
    if eff >= e_cut:
        return ("GRIND " if acc >= a_cut else "IMPULSE ") + dirn
    return "CONSOLIDATION" if acc >= a_cut else "WHIPSAW"


def grade(bars, atr: float | None = None, n_rows: int = N_ROWS, e_cut: float = E_CUT,
          a_cut: float = A_CUT, min_bars: int = MIN_BARS) -> Grade:
    """OHLCV DataFrame (>=1 row) -> Grade. `atr` optional, only for `scale`.

    `n_rows`/`e_cut`/`a_cut`/`min_bars` are the regime knobs (default = the module
    constants); callers pass config-resolved values so grade() is tunable while
    staying a pure function (no config import). Same inputs -> same Grade."""
    o = bars["open"].to_numpy(float)
    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    c = bars["close"].to_numpy(float)
    v = bars["volume"].to_numpy(float)
    n = len(c)

    O, C, H, L = float(o[0]), float(c[-1]), float(h.max()), float(l.min())
    rng = (H - L) or 1e-9
    net = C - O
    diffs = np.diff(c)
    travel = float(np.abs(diffs).sum()) or 1e-9
    signs = np.sign(diffs); signs = signs[signs != 0]
    swings = int((np.diff(signs) != 0).sum()) if len(signs) > 1 else 0

    base, rs, poc_i, va_lo, va_hi = _profile(h, l, v, n_rows)
    poc = base + (poc_i + 0.5) * rs
    vah = base + (va_hi + 1) * rs
    val = base + va_lo * rs
    va_frac = (va_hi - va_lo + 1) / n_rows
    acceptance = 1 - va_frac

    direction = "bull" if net > 0 else "bear" if net < 0 else "flat"
    efficiency = abs(net) / travel
    state = _classify(efficiency, acceptance, direction, n >= min_bars, e_cut, a_cut)

    return Grade(
        direction=direction, net=net, range=rng, strength=net / rng,
        travel=travel, efficiency=efficiency, swings=swings,
        body_pct=abs(net) / rng, close_pos=(C - L) / rng,
        up_wick=(H - max(O, C)) / rng, low_wick=(min(O, C) - L) / rng,
        t_high=int(h.argmax()) / n, t_low=int(l.argmin()) / n,
        vol=float(v.sum()), delta=float(v[c >= o].sum() - v[c < o].sum()),
        poc=poc, vah=vah, val=val, va_frac=va_frac, poc_loc=(poc - L) / rng,
        acceptance=acceptance, scale=(rng / atr if atr else None),
        state=state, meta={"open": O, "high": H, "low": L, "close": C, "volume": float(v.sum())},
    )
