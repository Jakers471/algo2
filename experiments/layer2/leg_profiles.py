"""experiments/layer2/leg_profiles.py — TEMP throwaway. Volume profile per leg.

Hangs a volume profile off each LEG (not the session) and grades it by how
CONCENTRATED the volume is:

  - IMPULSE  leg: price ran through -> volume spread over many rows -> WIDE value
    area (high va_frac).
  - RANGE    leg: price accepted   -> volume piled at a POC -> NARROW value area
    (low va_frac) = a consolidation.

So `va_frac` (fraction of the leg's rows that hold 70% of its volume) is the
impulse-vs-consolidation score — volume-based, replacing leg count and the removed
range boxes. Draws chop #2 and the strongest bull (contrast) with each leg's
profile hung in place.

  python experiments/layer2/leg_profiles.py
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from session_legs import zigzag, pick_sessions  # noqa: E402
from src.indicators.volume_profile import _profile_for, _value_area  # noqa: E402


def leg_profile(seg, n_rows=24):
    highs = seg["high"].values.astype(float)
    lows = seg["low"].values.astype(float)
    vols = seg["volume"].values.astype(float)
    lo, hi = float(lows.min()), float(highs.max())
    rng = (hi - lo) or 1e-9
    rs = rng / n_rows
    binvol = _profile_for(highs, lows, vols, range(len(seg)), lo, rs, n_rows)
    if binvol.sum() <= 0:
        return lo, rs, binvol, 0, 1.0
    poc = int(binvol.argmax())
    va_lo, va_hi = _value_area(binvol, poc, 0.70)
    return lo, rs, binvol, poc, (va_hi - va_lo + 1) / n_rows


def plot(ax, win, title, swing_frac, va_thr):
    o, h, l, c = (win[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    srange = h.max() - l.min()
    piv = zigzag(h, l, swing_frac * srange)

    for k in range(1, len(piv)):                         # per-leg volume profiles
        i0, i1 = piv[k - 1][0], piv[k][0]
        if i1 - i0 < 3:
            continue
        seg = win.iloc[i0:i1 + 1]
        base, rs, binvol, poc, va_frac = leg_profile(seg)
        is_range = va_frac < va_thr
        col = "#2b6cb0" if is_range else "#8a8f98"
        maxv = float(binvol.max()) or 1.0
        span = (i1 - i0) * 0.9
        for r in range(len(binvol)):
            w = binvol[r] / maxv * span
            ax.add_patch(Rectangle((i0, base + r * rs), w, rs, color=col,
                                   alpha=0.55 if r == poc else 0.20, lw=0, zorder=1))
        ax.hlines(base + (poc + 0.5) * rs, i0, i1, color=col, lw=1.0, ls="--", zorder=1.5)
        ax.text((i0 + i1) / 2, h[i0:i1 + 1].max(), f"{'RANGE' if is_range else 'impulse'}\nva {va_frac:.0%}",
                fontsize=6.5, ha="center", va="bottom", zorder=6,
                color="#2b6cb0" if is_range else "#666", weight="bold" if is_range else "normal")

    for i in range(n):                                   # candles
        cc = "#1a9850" if c[i] >= o[i] else "#d73027"
        ax.plot([i, i], [l[i], h[i]], color=cc, lw=0.4, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or 0.01, color=cc, lw=0, zorder=2))
    for k in range(1, len(piv)):                         # zigzag
        (i0, p0, _), (i1, p1, _) = piv[k - 1], piv[k]
        ax.plot([i0, i1], [p0, p1], color="#111", lw=1.2, zorder=3)

    ax.set_title(title, fontsize=10, loc="left")
    ax.set_xlim(-2, n + 2)
    ax.tick_params(labelsize=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--start", default="2024-09-01")
    ap.add_argument("--swing_frac", type=float, default=0.20)
    ap.add_argument("--va_thr", type=float, default=0.55, help="value-area frac below which a leg is a RANGE")
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", args.symbol, f"{args.symbol}_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", args.symbol, f"{args.symbol}_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]

    picks = pick_sessions(d5)
    chosen = [picks[3], picks[0]]                        # chop #2, strongest bull
    fig, axes = plt.subplots(2, 1, figsize=(16, 11))
    for ((netp, t0, t1), label), ax in zip(chosen, axes):
        win = d1.loc[(d1.index >= t0) & (d1.index <= t1 + pd.Timedelta("5min"))]
        plot(ax, win, f"{label}   NY {t0.date()}   (Layer1 net {netp:+.0%})", args.swing_frac, args.va_thr)
    fig.suptitle("Layer 2 — a volume profile hung off each leg. "
                 "Fat POC / narrow value area (blue) = consolidation; spread = impulse.", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(HERE, "leg_profiles.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
