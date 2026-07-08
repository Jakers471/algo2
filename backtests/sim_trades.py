"""backtests/sim_trades.py — render individual trades as 1-min candlesticks.

For the chosen manage config, replay each trade recording its FULL lifecycle (entry, initial
stop, every trailing-stop step, exit) and draw it on local 1-min candles: VAH/VAL of the base,
entry marker, initial stop, the trailing-stop staircase, and the exit (where + why it closed).
10 winners + 10 losers -> two PNGs. Everything is one price scale (local data), so it aligns.
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

START, END = "2018-01-01", "2025-01-01"
CFG = dict(stop_mult=1.5, be_trigger=None, target_R=None, trail_R=2.0)   # wider 1.5 + trail 2R
OUTDIR = os.path.dirname(os.path.abspath(__file__))
UP, DN = "#26a69a", "#ef5350"


def trace(h, l, c, tr, cfg):
    """Replay one trade, recording the stop staircase + exit."""
    long = tr["direction"] == "long"
    entry, vaw = tr["entry"], tr["va_width"]
    Rd = cfg["stop_mult"] * vaw
    if Rd <= 0:
        return None
    stop0 = entry - Rd if long else entry + Rd
    stop = stop0
    target = None
    if cfg.get("target_R"):
        target = entry + cfg["target_R"] * Rd if long else entry - cfg["target_R"] * Rd
    peak = entry; be_done = False
    path = [(tr["entry_idx"], stop)]                    # (bar, stop level) staircase
    for k in range(tr["entry_idx"] + 1, tr["end_idx"] + 1):
        hi, lo = h[k], l[k]
        hit_stop = lo <= stop if long else hi >= stop
        hit_tgt = (target is not None) and (hi >= target if long else lo <= target)
        if hit_stop:
            moved = abs(stop - stop0) > 1e-9
            R = (stop - entry) / Rd * (1 if long else -1)
            return dict(tr, exit_idx=k, exit=stop, reason="trail" if moved else "stop",
                        R=R, path=path, stop0=stop0, Rd=Rd, target=target)
        if hit_tgt:
            R = (target - entry) / Rd * (1 if long else -1)
            return dict(tr, exit_idx=k, exit=target, reason="target", R=R, path=path,
                        stop0=stop0, Rd=Rd, target=target)
        peak = max(peak, hi) if long else min(peak, lo)
        if cfg.get("be_trigger") and not be_done:
            if ((peak - entry) >= cfg["be_trigger"] * Rd) if long else ((entry - peak) >= cfg["be_trigger"] * Rd):
                stop = entry; be_done = True; path.append((k, stop))
        if cfg.get("trail_R"):
            ns = max(stop, peak - cfg["trail_R"] * Rd) if long else min(stop, peak + cfg["trail_R"] * Rd)
            if abs(ns - stop) > 1e-9:
                stop = ns; path.append((k, stop))
    R = (c[tr["end_idx"]] - entry) / Rd * (1 if long else -1)
    return dict(tr, exit_idx=tr["end_idx"], exit=c[tr["end_idx"]], reason="session_close",
                R=R, path=path, stop0=stop0, Rd=Rd, target=target)


def draw(ax, o, h, l, c, times, t):
    long = t["direction"] == "long"
    e, x = t["entry_idx"], t["exit_idx"]
    a = max(0, e - 35); b = min(len(c) - 1, x + 8)
    rng = range(a, b + 1)
    for i in rng:                                          # candlesticks
        col = UP if c[i] >= o[i] else DN
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.7, zorder=1)
        ax.add_patch(Rectangle((i - 0.32, min(o[i], c[i])), 0.64, abs(c[i] - o[i]) or 1e-6,
                               facecolor=col, edgecolor=col, zorder=2))
    # base value area (the consolidation the break came from)
    ax.axhline(t["vah"], color="#5c6bc0", ls=":", lw=1.0, zorder=3)
    ax.axhline(t["val"], color="#5c6bc0", ls=":", lw=1.0, zorder=3)
    ax.text(a, t["vah"], " VAH", color="#5c6bc0", fontsize=6, va="bottom")
    ax.text(a, t["val"], " VAL", color="#5c6bc0", fontsize=6, va="top")
    # entry
    ax.scatter([e], [t["entry"]], marker="^" if long else "v", s=70,
               color="#1565c0", zorder=6, edgecolor="white", lw=0.5)
    # initial stop (dashed red) across the trade
    ax.plot([e, x], [t["stop0"], t["stop0"]], color=DN, ls="--", lw=1.0, zorder=4)
    ax.text(e, t["stop0"], " stop", color=DN, fontsize=6, va="top")
    # trailing-stop staircase (orange step line, extended to exit)
    px = [p[0] for p in t["path"]] + [x]; py = [p[1] for p in t["path"]] + [t["path"][-1][1]]
    ax.step(px, py, where="post", color="#fb8c00", lw=1.3, zorder=5)
    if t["target"] is not None:
        ax.plot([e, x], [t["target"], t["target"]], color=UP, ls="--", lw=1.0, zorder=4)
    # exit
    win = t["R"] > 0
    ax.scatter([x], [t["exit"]], marker="X", s=90, color=UP if win else DN,
               zorder=7, edgecolor="white", lw=0.6)
    # x ticks: a few times
    ticks = np.linspace(a, b, 4).astype(int)
    ax.set_xticks(ticks)
    ax.set_xticklabels([times[i].strftime("%m/%d %H:%M") for i in ticks], fontsize=6)
    ax.tick_params(labelsize=6)
    ax.set_title(f"{t['direction'].upper()}  {t['R']:+.2f}R  ({t['reason']})  "
                 f"{times[e].strftime('%Y-%m-%d %H:%M')}  VA={t['va_width']:.0f}pt",
                 fontsize=8)
    ax.grid(alpha=0.15)


def grid(o, h, l, c, times, traces, title, out):
    fig, axes = plt.subplots(5, 2, figsize=(13, 18))
    for ax, t in zip(axes.ravel(), traces):
        draw(ax, o, h, l, c, times, t)
    fig.suptitle(title, fontsize=13, y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.99])
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print("wrote", out)


def main():
    o, h, l, c, v, mod, epoch = sim.load(START, END)
    key = os.path.join(sim.CACHE, f"trades_{START}_{END}.pkl")
    if os.path.exists(key):
        trades = pickle.load(open(key, "rb"))
        print(f"loaded {len(trades)} cached base trades")
    else:
        print(f"{len(c):,} 1m bars; grading rolling states (one-time, ~minutes) ...")
        st = sim.rolling_states(o, h, l, c, v)
        trades = sim.generate_trades(o, h, l, c, v, mod, epoch, st)
        pickle.dump(trades, open(key, "wb"))
        print(f"{len(trades)} base trades cached")

    df = pd.read_parquet(sim.DATA)
    df = df.loc[(df.index >= pd.Timestamp(START, tz="UTC")) & (df.index < pd.Timestamp(END, tz="UTC"))]
    times = df.tz_convert("America/Chicago").index

    tr = [t for t in (trace(h, l, c, x, CFG) for x in trades) if t is not None]
    wins = sorted([t for t in tr if t["R"] > 0], key=lambda t: t["R"], reverse=True)
    losses = sorted([t for t in tr if t["R"] <= 0], key=lambda t: t["R"])
    n = len(tr); w = sum(1 for t in tr if t["R"] > 0)
    print(f"config wider1.5+trail2R: {n} trades, {100*w/n:.0f}% win, {sum(t['R'] for t in tr):+.0f}R total")

    # 10 winners spread across the R range (small..huge), 10 losers
    def spread(lst, k):
        if len(lst) <= k:
            return lst
        return [lst[int(i)] for i in np.linspace(0, len(lst) - 1, k)]
    grid(o, h, l, c, times, spread(wins, 10),
         f"WINNERS — wider 1.5 stop + trail 2R  ({START[:4]}-{END[:4]})", os.path.join(OUTDIR, "sim_winners.png"))
    grid(o, h, l, c, times, spread(losses, 10),
         f"LOSERS — wider 1.5 stop + trail 2R  ({START[:4]}-{END[:4]})", os.path.join(OUTDIR, "sim_losers.png"))


if __name__ == "__main__":
    main()
