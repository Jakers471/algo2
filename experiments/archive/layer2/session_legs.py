"""experiments/layer2/session_legs.py — TEMP throwaway. Layer 2: legs within a session.

Takes a session (picked at Layer 1 on 5m) and runs the SAME engine — directional
legs + retracement — on its 1-MINUTE bars, to reveal the internal sequence Layer 1
collapses away. A session Layer 1 calls "chop" should decompose into
impulse -> range -> impulse -> range whose legs cancel out.

  - ZIGZAG: swing legs, where a leg only reverses after price retraces it by a
    threshold (= `swing_frac` of the session's range). Green up, red down.
  (Consolidation detection will be volume-profile-based next — the crude local-range
  boxes were removed.)

Plots the same 4 NY sessions as the Layer 1 anatomy (strongest bull/bear, 2 flattest)
so you can see zoomed-in structure vs the one-word Layer 1 verdict.

  python experiments/layer2/session_legs.py
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # experiments/archive/... -> repo
sys.path.insert(0, REPO)
from src.indicators.sessions import session_instances  # noqa: E402


def zigzag(h, l, thr):
    """Threshold zigzag -> list of pivots (idx, price, 'H'|'L')."""
    n = len(h)
    piv = []
    up = None
    hi_i, lo_i = 0, 0
    for i in range(1, n):
        if h[i] > h[hi_i]:
            hi_i = i
        if l[i] < l[lo_i]:
            lo_i = i
        if up is None:
            if h[hi_i] - l[i] >= thr:
                piv.append((hi_i, h[hi_i], "H")); up = False; lo_i = i
            elif h[i] - l[lo_i] >= thr:
                piv.append((lo_i, l[lo_i], "L")); up = True; hi_i = i
        elif up:                              # looking for a swing high
            if h[i] > h[hi_i]:
                hi_i = i
            if h[hi_i] - l[i] >= thr:
                piv.append((hi_i, h[hi_i], "H")); up = False; lo_i = i
        else:                                 # looking for a swing low
            if l[i] < l[lo_i]:
                lo_i = i
            if h[i] - l[lo_i] >= thr:
                piv.append((lo_i, l[lo_i], "L")); up = True; hi_i = i
    # close with the running extreme
    if up:
        piv.append((hi_i, h[hi_i], "H"))
    elif up is False:
        piv.append((lo_i, l[lo_i], "L"))
    return piv


def plot_legs(ax, win, title, swing_frac):
    o, h, l, c = (win[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    srange = h.max() - l.min()

    for i in range(n):                          # candles
        cc = "#1a9850" if c[i] >= o[i] else "#d73027"
        ax.plot([i, i], [l[i], h[i]], color=cc, lw=0.4, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or 0.01, color=cc, lw=0, zorder=2))

    piv = zigzag(h, l, swing_frac * srange)
    for k in range(1, len(piv)):
        (i0, p0, _), (i1, p1, _) = piv[k - 1], piv[k]
        up = p1 >= p0
        ax.plot([i0, i1], [p0, p1], color="#111", lw=1.4, zorder=4)
        ax.text((i0 + i1) / 2, (p0 + p1) / 2, f"{p1 - p0:+.0f}", fontsize=6.5, zorder=5,
                color="#1a7a3a" if up else "#b3261e", ha="center",
                va="bottom" if up else "top", weight="bold")

    n_up = sum(1 for k in range(1, len(piv)) if piv[k][1] >= piv[k - 1][1])
    n_dn = len(piv) - 1 - n_up
    ax.text(0.01, 0.98, f"{len(piv)-1} legs  ({n_up} up / {n_dn} down)",
            transform=ax.transAxes, va="top", fontsize=8, family="monospace",
            bbox=dict(boxstyle="round", fc="white", ec="#ccc", alpha=0.9))
    ax.set_title(title, fontsize=10, loc="left")
    ax.set_xlim(-2, n + 2)
    ax.tick_params(labelsize=7)


def pick_sessions(df5):
    ny = [s for s in session_instances(df5, 1_000_000) if s["session"] == "NY"]
    scored = []
    for s in ny:
        w = df5.iloc[s["start_pos"]:s["end_pos"] + 1]
        rng = float(w["high"].max() - w["low"].min()) or 1e-9
        netp = float(w["close"].iloc[-1] - w["open"].iloc[0]) / rng
        scored.append((netp, df5.index[s["start_pos"]], df5.index[s["end_pos"]]))
    scored.sort()
    flat = sorted(scored, key=lambda x: abs(x[0]))[:2]
    return [(scored[-1], "STRONGEST BULL"), (scored[0], "STRONGEST BEAR"),
            (flat[0], "FLATTEST (chop) #1"), (flat[1], "FLATTEST (chop) #2")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--start", default="2024-09-01")
    ap.add_argument("--swing_frac", type=float, default=0.15)
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", args.symbol, f"{args.symbol}_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", args.symbol, f"{args.symbol}_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]

    picks = pick_sessions(d5)
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    for ((netp, t0, t1), label), ax in zip(picks, axes.ravel()):
        win = d1.loc[(d1.index >= t0) & (d1.index <= t1 + pd.Timedelta("5min"))]
        plot_legs(ax, win, f"{label}   NY {t0.date()}   (Layer1 net {netp:+.0%})",
                  args.swing_frac)
    fig.suptitle("Layer 2 — same session on 1-min bars: legs (zigzag). "
                 "Chop = impulses that cancel.", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(HERE, "session_legs.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
