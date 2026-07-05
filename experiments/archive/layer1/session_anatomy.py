"""experiments/session_anatomy.py — TEMP throwaway. Every dimension of ONE session.

Grades each session atomically (no cross-session context) on everything derivable
from its own bars, then plots a contrasting set of NY sessions — the most directional
and the flattest — so we can see the raw features a regime could be built from.

  python experiments/session_anatomy.py
"""
from __future__ import annotations

import argparse
import math
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
from src.indicators.volume_profile import _profile_for  # noqa: E402 (overlap-weighted rows)


def profile(win, row_size=5.0):
    """Session volume profile (same overlap-weighted math the chart uses).
    -> (base, row_size, binvol[n_rows], poc_idx, poc_price)."""
    highs = win["high"].values.astype(float)
    lows = win["low"].values.astype(float)
    vols = win["volume"].values.astype(float)
    lo, hi = float(lows.min()), float(highs.max())
    base = math.floor(lo / row_size) * row_size
    top = math.ceil(hi / row_size) * row_size
    n_rows = max(1, int(round((top - base) / row_size)))
    binvol = _profile_for(highs, lows, vols, range(len(win)), base, row_size, n_rows)
    poc_idx = int(binvol.argmax())
    return base, row_size, binvol, poc_idx, base + (poc_idx + 0.5) * row_size


def dims(win):
    o, h, l, c = (win[k].values.astype(float) for k in ("open", "high", "low", "close"))
    v = win["volume"].values.astype(float)
    O, C, H, L = float(o[0]), float(c[-1]), float(h.max()), float(l.min())
    rng = H - L or 1e-9
    net = C - O
    diffs = np.diff(c)
    travel = float(np.abs(diffs).sum()) or 1e-9
    signs = np.sign(diffs); signs = signs[signs != 0]
    swings = int((np.diff(signs) != 0).sum()) if len(signs) > 1 else 0
    return {
        "O": O, "C": C, "H": H, "L": L, "rng": rng, "net": net,
        "net_pct": net / rng,                      # -1 strong bear .. +1 strong bull
        "body_pct": abs(net) / rng,
        "close_pos": (C - L) / rng,                # 0 = closed on low, 1 = on high
        "up_wick": (H - max(O, C)) / rng,
        "low_wick": (min(O, C) - L) / rng,
        "travel": travel,
        "path_eff": rng / travel,                  # 0 choppy .. 1 clean one-way move
        "swings": swings,                          # intrabar direction changes
        "t_high": int(h.argmax()) / len(h),        # when the high formed (0 start..1 end)
        "t_low": int(l.argmin()) / len(l),
        "vol": float(v.sum()),
        "delta": float(v[c >= o].sum() - v[c < o].sum()),
        "nbars": len(c),
    }


def plot_session(ax, win, d, title):
    o, h, l, c = (win[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    # fib levels of the session leg
    for f in (0.236, 0.382, 0.5, 0.618, 0.786):
        y = d["L"] + f * d["rng"]
        ax.axhline(y, color="#bbb", lw=0.5, ls=":")
        if f in (0.5, 0.618):
            ax.text(n - 0.5, y, f" {f:.3f}", fontsize=6, color="#999", va="center")
    ax.axhline(d["H"], color="#555", lw=0.7)
    ax.axhline(d["L"], color="#555", lw=0.7)

    # volume profile: horizontal histogram off the left edge, POC line across
    base, rs, binvol, poc_idx, poc_price = profile(win)
    maxv = float(binvol.max()) or 1.0
    pw = n * 0.26                                                # profile width (x units)
    for i in range(len(binvol)):
        w = binvol[i] / maxv * pw
        if w <= 0:
            continue
        ax.add_patch(Rectangle((-pw - 1 + (pw - w), base + i * rs), w, rs,
                               color="#e08a1e" if i == poc_idx else "#9aa6b0",
                               alpha=0.6 if i == poc_idx else 0.35, lw=0, zorder=1))
    ax.axhline(poc_price, color="#e08a1e", lw=1.0, ls="--", zorder=2)
    ax.text(n + 4, poc_price, " POC", color="#e08a1e", fontsize=6.5, va="center")

    ax.plot(range(n), c, color="#3573b9", lw=0.7, alpha=0.6)     # close path (shows travel)
    for i in range(n):
        up = c[i] >= o[i]
        cc = "#1a9850" if up else "#d73027"
        ax.plot([i, i], [l[i], h[i]], color=cc, lw=0.5)
        ax.add_patch(Rectangle((i - 0.34, min(o[i], c[i])), 0.68, abs(c[i] - o[i]) or 0.01, color=cc, lw=0, zorder=3))
    ax.plot(0, d["O"], "o", color="#000", ms=4)                  # open
    ax.plot(n - 1, d["C"], ">", color="#000", ms=6)             # close
    ax.set_xlim(-pw - 3, n + 8)

    poc_pos = (poc_price - d["L"]) / d["rng"]
    txt = (f"range {d['rng']:.0f} pts   ({d['nbars']} bars)\n"
           f"net {d['net']:+.0f}  =  {d['net_pct']:+.0%} of range   <- direction/strength\n"
           f"closed at {d['close_pos']:.0%} of range\n"
           f"body {d['body_pct']:.0%} | up-wick {d['up_wick']:.0%} | low-wick {d['low_wick']:.0%}\n"
           f"travel {d['travel']:.0f} pts | efficiency {d['path_eff']:.2f}\n"
           f"direction changes {d['swings']} | high formed {d['t_high']:.0%} in\n"
           f"volume {d['vol']/1e3:.0f}k | delta {d['delta']/1e3:+.0f}k\n"
           f"POC @ {poc_price:.0f}  ({poc_pos:.0%} of range)")
    ax.text(0.015, 0.985, txt, transform=ax.transAxes, va="top", ha="left", fontsize=7.3,
            family="monospace", bbox=dict(boxstyle="round", fc="white", ec="#ccc", alpha=0.9))
    ax.set_title(title, fontsize=10, loc="left")
    ax.tick_params(labelsize=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--start", default="2024-09-01")
    args = ap.parse_args()

    path = os.path.join(REPO, "data", args.symbol, f"{args.symbol}_{args.tf}.parquet")
    df = pd.read_parquet(path)
    df = df.loc[df.index >= pd.Timestamp(args.start, tz="UTC")]
    insts = [s for s in session_instances(df, max_sessions=1_000_000) if s["session"] == "NY"]

    entries = []
    for s in insts:
        win = df.iloc[s["start_pos"]:s["end_pos"] + 1]
        if len(win) < 10:
            continue
        entries.append((s, win, dims(win)))

    entries.sort(key=lambda e: e[2]["net_pct"])
    picks = [
        (entries[-1], "STRONGEST BULL"),        # most positive net%
        (entries[0], "STRONGEST BEAR"),         # most negative net%
    ]
    flat = sorted(entries, key=lambda e: abs(e[2]["net_pct"]))[:2]   # nearest zero = chop
    picks += [(flat[0], "FLATTEST (chop) #1"), (flat[1], "FLATTEST (chop) #2")]

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    for (entry, label), ax in zip(picks, axes.ravel()):
        s, win, d = entry
        date = str(win.index[0].date())
        plot_session(ax, win, d, f"{label}   NY {date}")
    fig.suptitle("Anatomy of one session — dimensions extractable from a single NY session", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(HERE, "session_anatomy.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
