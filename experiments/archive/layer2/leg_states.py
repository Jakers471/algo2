"""experiments/layer2/leg_states.py — TEMP throwaway. The 2-axis regime map.

Every regime is two independent axes measured over a rolling window:

  PROGRESS  = efficiency = |net move| / total travel   (did price actually go somewhere?)
  ACCEPTANCE = volume concentration = 1 - va_frac       (did volume pile at a POC?)

Crossed, they give four states (progress states also carry up/down direction):

                 low acceptance (spread)     high acceptance (fat POC)
  net progress   IMPULSE (green/red)         GRIND / accumulation (pale green/red)
  no progress    WHIPSAW (gray)              CONSOLIDATION (blue)

A zigzag leg is always "progress" by construction, so the classifier is rolling
(per bar over a window), not per-leg — that's why "no progress" states can exist.
Colors the candles by state. Chop #2 + strongest bull.

  python experiments/layer2/leg_states.py
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from session_legs import pick_sessions  # noqa: E402
from src.indicators.volume_profile import _profile_for, _value_area  # noqa: E402

COLORS = {
    "IMPULSE UP": "#1a9850", "IMPULSE DN": "#d73027",
    "GRIND UP": "#a7d8a0", "GRIND DN": "#f0a9a0",
    "CONSOLIDATION": "#5a8fd0", "WHIPSAW": "#b3b3b3",
}


def va_frac(h, l, v, n_rows=20):
    lo, hi = float(l.min()), float(h.max())
    rng = (hi - lo) or 1e-9
    rs = rng / n_rows
    binvol = _profile_for(h, l, v, range(len(h)), lo, rs, n_rows)
    if binvol.sum() <= 0:
        return 1.0
    poc = int(binvol.argmax())
    a, b = _value_area(binvol, poc, 0.70)
    return (b - a + 1) / n_rows


def classify(df, w, prog_cut, acc_cut):
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    v = df["volume"].values.astype(float)
    c = df["close"].values.astype(float)
    n = len(c)
    states = [None] * n
    for i in range(w, n):
        seg = slice(i - w, i + 1)
        cc = c[seg]
        travel = float(np.abs(np.diff(cc)).sum()) or 1e-9
        prog = abs(cc[-1] - cc[0]) / travel
        acc = 1 - va_frac(h[seg], l[seg], v[seg])
        directional = prog >= prog_cut
        accepted = acc >= acc_cut
        if directional:
            up = cc[-1] >= cc[0]
            base = "GRIND" if accepted else "IMPULSE"
            states[i] = f"{base} {'UP' if up else 'DN'}"
        else:
            states[i] = "CONSOLIDATION" if accepted else "WHIPSAW"
    return states


def plot(ax, df, title, w, prog_cut, acc_cut):
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    states = classify(df, w, prog_cut, acc_cut)
    ylo, yhi = l.min(), h.max()

    i = w
    while i < n:                                    # shade contiguous state runs
        j = i
        while j < n and states[j] == states[i]:
            j += 1
        ax.add_patch(Rectangle((i - 0.5, ylo), j - i, yhi - ylo,
                               color=COLORS.get(states[i], "#fff"), alpha=0.20, lw=0, zorder=1))
        i = j

    for k in range(n):                              # candles
        cc = "#111" if c[k] >= o[k] else "#444"
        ax.plot([k, k], [l[k], h[k]], color=cc, lw=0.4, zorder=2)
        ax.add_patch(Rectangle((k - 0.3, min(o[k], c[k])), 0.6, abs(c[k] - o[k]) or 0.01, color=cc, lw=0, zorder=2))

    ax.set_title(title, fontsize=10, loc="left")
    ax.set_xlim(-2, n + 2)
    ax.set_ylim(ylo - (yhi - ylo) * 0.03, yhi + (yhi - ylo) * 0.03)
    ax.tick_params(labelsize=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--start", default="2024-09-01")
    ap.add_argument("--window", type=int, default=35)
    ap.add_argument("--prog_cut", type=float, default=0.38, help="efficiency above = directional")
    ap.add_argument("--acc_cut", type=float, default=0.55, help="concentration above = accepted")
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", args.symbol, f"{args.symbol}_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", args.symbol, f"{args.symbol}_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]

    picks = pick_sessions(d5)
    chosen = [picks[3], picks[0]]                   # chop #2, strongest bull
    fig, axes = plt.subplots(2, 1, figsize=(16, 11))
    for ((netp, t0, t1), label), ax in zip(chosen, axes):
        win = d1.loc[(d1.index >= t0) & (d1.index <= t1 + pd.Timedelta("5min"))]
        plot(ax, win, f"{label}   NY {t0.date()}   (Layer1 net {netp:+.0%})",
             args.window, args.prog_cut, args.acc_cut)
    handles = [Patch(color=v, alpha=0.5, label=k) for k, v in COLORS.items()]
    axes[0].legend(handles=handles, ncol=6, fontsize=8, loc="upper center",
                   bbox_to_anchor=(0.5, 1.28), frameon=False)
    fig.suptitle("Layer 2 — the 2-axis regime map: PROGRESS x ACCEPTANCE, rolling per bar.", fontsize=12, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(HERE, "leg_states.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
