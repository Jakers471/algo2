"""experiments/regime_plot.py — TEMP throwaway. Visual-check the regime labels.

Runs the regime analysis, then finds representative windows — the longest bullish
structural run, the longest bearish run, and the lowest-efficiency (choppiest)
window — and plots each as candlesticks with the per-session regime shaded behind,
so you can eyeball whether the labels match the price action.

  python experiments/regime_plot.py                 # -> writes a PNG, prints its path
  python experiments/regime_plot.py --start 2024-01-01 --sessions 6
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
REPO = os.path.dirname(os.path.dirname(HERE))   # experiments/archive -> repo root
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from regime import analyze  # noqa: E402
from src.indicators.sessions import session_instances  # noqa: E402

# regime -> (fill color, alpha, short label)
RC = {
    "TREND UP": ("#1a9850", 0.20), "REVERSAL UP": ("#1a9850", 0.20),
    "BULL PULLBACK": ("#66bd63", 0.11),
    "TREND DOWN": ("#d73027", 0.20), "REVERSAL DOWN": ("#d73027", 0.20),
    "BEAR PULLBACK": ("#f46d43", 0.11),
    "FUZZY": ("#888888", 0.13),
    "CONSOLIDATION": ("#4575b4", 0.18),
}


def longest_run(rows, side):
    best = (0, 0, 0)
    i = 0
    while i < len(rows):
        if rows[i]["trend"] == side:
            j = i
            while j < len(rows) and rows[j]["trend"] == side:
                j += 1
            if j - i > best[0]:
                best = (j - i, i, j)
            i = j
        else:
            i += 1
    return best[1], best[2]   # [start, end) session indices


def choppiest(rows, closes_by_sess, w):
    """Rolling efficiency ratio; return the lowest-efficiency window (session idx)."""
    best_eff, best_i = 2.0, 0
    for i in range(len(rows) - w):
        seg = closes_by_sess[i:i + w + 1]
        net = abs(seg[-1] - seg[0])
        path = sum(abs(seg[k] - seg[k - 1]) for k in range(1, len(seg)))
        eff = net / path if path else 1.0
        if eff < best_eff:
            best_eff, best_i = eff, i
    return best_i, best_i + w + 1


def plot_window(ax, df, insts, rows, a, b, title):
    """Plot sessions [a, b) as candles + regime shading."""
    p0 = insts[a]["start_pos"]
    p1 = insts[b - 1]["end_pos"]
    win = df.iloc[p0:p1 + 1]
    o, h, l, c = win["open"].values, win["high"].values, win["low"].values, win["close"].values

    for j in range(a, b):                       # regime shading + session H/L
        xs = insts[j]["start_pos"] - p0
        xe = insts[j]["end_pos"] - p0
        reg = rows[j]["regime"]
        col, al = RC.get(reg, ("#888888", 0.12))
        ax.axvspan(xs - 0.5, xe + 0.5, color=col, alpha=al, lw=0)
        ax.hlines(insts[j]["hi_price"], xs, xe, color="#333", lw=0.5, alpha=0.4)
        ax.hlines(insts[j]["lo_price"], xs, xe, color="#333", lw=0.5, alpha=0.4)
        ax.text((xs + xe) / 2, ax_top(h), reg.replace(" ", "\n"), ha="center",
                va="top", fontsize=6.5, color=col if al > 0.15 else "#555")

    for i in range(len(win)):                   # candles
        up = c[i] >= o[i]
        cc = "#1a9850" if up else "#d73027"
        ax.plot([i, i], [l[i], h[i]], color=cc, lw=0.5)
        ax.add_patch(Rectangle((i - 0.34, min(o[i], c[i])), 0.68, abs(c[i] - o[i]) or 0.01,
                               color=cc, lw=0))
    ax.set_xlim(-1, len(win))
    d0 = str(win.index[0].date())
    ax.set_title(f"{title}   ({d0}, {b - a} sessions)", fontsize=10, loc="left")
    ax.tick_params(labelbottom=False, labelsize=7)


_AX_TOP = {}
def ax_top(h):
    return h.max() + (h.max() - h.min()) * 0.02


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--sessions", type=int, default=6, help="max sessions per example")
    args = ap.parse_args()

    path = os.path.join(REPO, "data", args.symbol, f"{args.symbol}_{args.tf}.parquet")
    df = pd.read_parquet(path)
    df = df.loc[df.index >= pd.Timestamp(args.start, tz="UTC")]
    rows = analyze(df, args.start, 0.50, 0.70, 1.5, 4)
    insts = session_instances(df, max_sessions=1_000_000)
    closes = df["close"].values
    closes_by_sess = [float(closes[s["end_pos"]]) for s in insts]

    def clip(a, b):                             # cap window to --sessions
        return a, min(b, a + args.sessions)

    ba, bb = clip(*longest_run(rows, "bull"))
    ra, rb = clip(*longest_run(rows, "bear"))
    ca, cb = choppiest(rows, closes_by_sess, args.sessions - 1)

    fig, axes = plt.subplots(3, 1, figsize=(15, 11))
    plot_window(axes[0], df, insts, rows, ba, bb, "BULLISH TREND")
    plot_window(axes[1], df, insts, rows, ra, rb, "BEARISH TREND")
    plot_window(axes[2], df, insts, rows, ca, cb, "CHOPPIEST (candidate consolidation)")
    fig.suptitle(f"{args.symbol} {args.tf} — regime examples  (green=bull, red=bear, blue=chop, gray=fuzzy)",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.98])

    out = os.path.join(REPO, "experiments", "regime_examples.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
