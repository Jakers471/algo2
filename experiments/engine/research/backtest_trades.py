"""experiments/engine/research/backtest_trades.py — draw real winners and losers.

Same rule as backtest_cont.py (VA breakout in a directional session, no lookahead), but
records each trade with enough context to draw it, then plots a grid of winners (left)
and losers (right): candles, the consolidation (blue), VAH/VAL, entry, stop (red),
target (green), and the exit.

  python experiments/engine/research/backtest_trades.py --sessions 200
"""
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
ENGINE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ENGINE))
sys.path.insert(0, ENGINE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import session_anchors, rolling_states  # noqa: E402
import viz  # noqa: E402


def cons_runs(states, min_len=15):
    out, i = [], 0
    while i < len(states):
        j = i
        while j < len(states) and states[j] == states[i]:
            j += 1
        if states[i] == "CONSOLIDATION" and j - i >= min_len:
            out.append((i, j - 1))
        i = j
    return out


def sim(entry, stop, target, side, h, l, c):
    for k in range(len(c)):
        if side == "long":
            if l[k] <= stop:
                return -1.0, k
            if h[k] >= target:
                return 2.0, k
        else:
            if h[k] >= stop:
                return -1.0, k
            if l[k] <= target:
                return 2.0, k
    R = (c[-1] - entry) / abs(entry - stop) * (1 if side == "long" else -1)
    return R, len(c) - 1


def collect(d5, d1, spans, bias_str=0.3):
    trades = []
    for s in spans:
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 60:
            continue
        st = rolling_states(win1, 25)
        h = win1["high"].to_numpy(float); l = win1["low"].to_numpy(float); c = win1["close"].to_numpy(float)
        for a, b in cons_runs(st):
            if a < 20 or b + 2 >= len(win1):
                continue
            g = grade(win1.iloc[a:b + 1]); vah, val = g.vah, g.val
            if vah <= val:
                continue
            gs = grade(win1.iloc[:a])
            bias = "long" if gs.strength >= bias_str else "short" if gs.strength <= -bias_str else None
            if bias is None:
                continue
            for k in range(b + 1, len(win1)):
                up_b, dn_b = c[k] > vah, c[k] < val
                if (bias == "long" and dn_b) or (bias == "short" and up_b):
                    break  # base broke the wrong way first -> abandon
                if (bias == "long" and up_b) or (bias == "short" and dn_b):
                    side = bias
                    entry = vah if side == "long" else val
                    stop = val if side == "long" else vah
                    risk = vah - val
                    target = entry + 2 * risk if side == "long" else entry - 2 * risk
                    R, exit_off = sim(entry, stop, target, side, h[k:], l[k:], c[k:])
                    exit_idx = k + exit_off
                    ws, we = max(0, a - 8), min(len(win1) - 1, exit_idx + 6)
                    trades.append(dict(win=win1.iloc[ws:we + 1], date=win1.index[a],
                                       cons=(a - ws, b - ws), vah=vah, val=val,
                                       entry_x=k - ws, entry=entry, stop=stop, target=target,
                                       exit_x=exit_idx - ws, side=side, R=R))
                    break
    return trades


def draw(ax, t):
    win = t["win"]; n = len(win)
    ca, cb = t["cons"]
    ylo = min(t["stop"], t["target"], win["low"].min())
    yhi = max(t["stop"], t["target"], win["high"].max())
    ax.add_patch(Rectangle((ca - 0.5, t["val"]), cb - ca + 1, t["vah"] - t["val"],
                           color="#7fb3e0", alpha=0.25, lw=0, zorder=1))
    ax.hlines([t["vah"], t["val"]], ca, t["exit_x"], color="#888", lw=0.7, ls=":", zorder=2)
    ax.hlines(t["stop"], t["entry_x"], t["exit_x"], color="#d73027", lw=1.2, ls="--", zorder=2)
    ax.hlines(t["target"], t["entry_x"], t["exit_x"], color="#1a9850", lw=1.2, ls="--", zorder=2)
    viz.candles(ax, win, zorder=3)
    mk = "^" if t["side"] == "long" else "v"
    ax.plot(t["entry_x"], t["entry"], mk, color="#000", ms=9, zorder=5)
    ax.plot(t["exit_x"], win["close"].iloc[t["exit_x"]], "o", color="#7a2fd0", ms=7, zorder=5)
    win_loss = "WIN" if t["R"] > 0 else "LOSS"
    ax.set_title(f"{t['side'].upper()} {win_loss} {t['R']:+.1f}R   {t['date'].tz_convert('America/Chicago').strftime('%Y-%m-%d %I%p')}",
                 fontsize=9, color="#1a7a3a" if t["R"] > 0 else "#b3261e", loc="left")
    ax.set_xlim(-1, n); ax.set_ylim(ylo - (yhi - ylo) * 0.05, yhi + (yhi - ylo) * 0.05)
    ax.tick_params(labelsize=6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--sessions", type=int, default=200)
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)[-args.sessions:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[spans[0]["start"]]]

    trades = collect(d5, d1, spans)
    wins = sorted([t for t in trades if t["R"] > 0], key=lambda t: -t["R"])[:4]
    loss = sorted([t for t in trades if t["R"] <= 0], key=lambda t: t["R"])[:4]
    print(f"{len(trades)} trades over {len(spans)} sessions ({d5.index[spans[0]['start']].date()} -> {d5.index[spans[-1]['end']].date()})"
          f"  |  {len([t for t in trades if t['R']>0])} win / {len([t for t in trades if t['R']<=0])} loss")

    fig, ax = plt.subplots(4, 2, figsize=(15, 15))
    for r in range(4):
        if r < len(wins):
            draw(ax[r, 0], wins[r])
        else:
            ax[r, 0].axis("off")
        if r < len(loss):
            draw(ax[r, 1], loss[r])
        else:
            ax[r, 1].axis("off")
    ax[0, 0].set_ylabel("WINNERS", fontsize=12, fontweight="bold")
    ax[0, 1].set_ylabel("LOSERS", fontsize=12, fontweight="bold")
    fig.suptitle("VA breakout trades - blue=consolidation, marker=entry, red=stop, green=target(2R), purple=exit",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    out = os.path.join(ENGINE, "out", "backtest_trades.png")
    fig.savefig(out, dpi=110); print("wrote", out)


if __name__ == "__main__":
    main()
