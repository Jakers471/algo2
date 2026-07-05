"""experiments/engine/research/find_continuation.py — up-leg -> consolidation -> up-leg.

Searches for a CONNECTED 3-phase bullish continuation at each scale:
  (IMPULSE UP or GRIND UP)  ->  CONSOLIDATION  ->  (IMPULSE UP or GRIND UP)
The three phases must be contiguous. Picks the clearest example (strongest up legs) at
each scale and draws it — candles with the three phases shaded and labeled.

  L3 = blocks of sessions (5m) · L1 = sessions (5m) · L2 = 1m state-runs in a session.

Read-only research VIEW; only calls the frozen engine.

  python experiments/engine/research/find_continuation.py
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

UP = {"IMPULSE UP", "GRIND UP"}


def reclass(g, e, a):
    d = "UP" if g.direction == "bull" else "DN"
    if g.efficiency >= e:
        return ("GRIND " if g.acceptance >= a else "IMPULSE ") + d
    return "CONSOLIDATION" if g.acceptance >= a else "WHIPSAW"


def runs(seq):
    out, i = [], 0
    while i < len(seq):
        j = i
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        out.append((seq[i], i, j - 1)); i = j
    return out


def merge_impulses(states, gap=12, min_len=8):
    n = len(states); raw = []; i = 0
    while i < n:
        if states[i] and states[i].startswith("IMPULSE"):
            j = i
            while j < n and states[j] == states[i]:
                j += 1
            raw.append([i, j - 1, states[i]]); i = j
        else:
            i += 1
    m = []
    for a, b, s in raw:
        if m and m[-1][2] == s and a - m[-1][1] - 1 <= gap:
            m[-1][1] = b
        else:
            m.append([a, b, s])
    return [(a, b, s) for a, b, s in m if b - a + 1 >= min_len]


def net(bars):
    return float(bars["close"].iloc[-1] - bars["open"].iloc[0])


def best(cands):
    """cands: [(bars, bounds, score)] -> the highest-score one, or None."""
    return max(cands, key=lambda c: c[2]) if cands else None


def find_l1(d5, insts):
    g = [grade(d5.iloc[s["start"]:s["end"] + 1]) for s in insts]
    e = float(np.median([x.efficiency for x in g])); a = float(np.median([x.acceptance for x in g]))
    st = [reclass(x, e, a) for x in g]
    cands = []
    for i in range(len(st) - 2):
        if st[i] in UP and st[i + 1] == "CONSOLIDATION" and st[i + 2] in UP:
            p0, p2 = insts[i]["start"], insts[i + 2]["end"]
            seg = d5.iloc[p0:p2 + 1]
            b = [(st[i], insts[i]["start"] - p0, insts[i]["end"] - p0),
                 (st[i + 1], insts[i + 1]["start"] - p0, insts[i + 1]["end"] - p0),
                 (st[i + 2], insts[i + 2]["start"] - p0, insts[i + 2]["end"] - p0)]
            score = net(d5.iloc[insts[i]["start"]:insts[i]["end"] + 1]) + net(d5.iloc[insts[i + 2]["start"]:insts[i + 2]["end"] + 1])
            cands.append((seg, b, score))
    return best(cands)


def find_l3(d5, insts, B=4):
    blocks = [(insts[j * B]["start"], insts[(j + 1) * B - 1]["end"]) for j in range((len(insts)) // B)]
    g = [grade(d5.iloc[s:e + 1]) for s, e in blocks]
    e_ = float(np.median([x.efficiency for x in g])); a_ = float(np.median([x.acceptance for x in g]))
    st = [reclass(x, e_, a_) for x in g]
    cands = []
    for i in range(len(st) - 2):
        if st[i] in UP and st[i + 1] == "CONSOLIDATION" and st[i + 2] in UP:
            p0, p2 = blocks[i][0], blocks[i + 2][1]
            seg = d5.iloc[p0:p2 + 1]
            b = [(st[i], blocks[i][0] - p0, blocks[i][1] - p0),
                 (st[i + 1], blocks[i + 1][0] - p0, blocks[i + 1][1] - p0),
                 (st[i + 2], blocks[i + 2][0] - p0, blocks[i + 2][1] - p0)]
            score = net(d5.iloc[blocks[i][0]:blocks[i][1] + 1]) + net(d5.iloc[blocks[i + 2][0]:blocks[i + 2][1] + 1])
            cands.append((seg, b, score))
    return best(cands)


def find_l2(d5, d1, insts, sample):
    """Two UP impulses with a CONSOLIDATION gap between them (within a session)."""
    cands = []
    for s in insts[-sample:]:
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 40:
            continue
        imps = merge_impulses(rolling_states(win1, 25))
        for k in range(1, len(imps)):
            pa, pb, px = imps[k - 1]
            ca, cb, cx = imps[k]
            if not (px.endswith("UP") and cx.endswith("UP")):
                continue
            gap = win1.iloc[pb + 1:ca]
            if len(gap) >= 8 and grade(gap).state == "CONSOLIDATION":
                seg = win1.iloc[pa:cb + 1]
                b = [("IMPULSE UP", 0, pb - pa),
                     ("CONSOLIDATION", pb - pa + 1, ca - pa - 1),
                     ("IMPULSE UP", ca - pa, cb - pa)]
                score = net(win1.iloc[pa:pb + 1]) + net(win1.iloc[ca:cb + 1])
                cands.append((seg, b, score))
    return best(cands)


def draw(ax, found, title):
    if not found:
        ax.text(0.5, 0.5, f"{title}\n(no connected example found)", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off"); return
    seg, bounds, _sc = found
    h = seg["high"].to_numpy(float); l = seg["low"].to_numpy(float)
    ylo, yhi = l.min(), h.max()
    for state, sa, sb in bounds:
        col = "#8fce8f" if state in UP else "#7fb3e0" if state == "CONSOLIDATION" else "#ccc"
        ax.add_patch(Rectangle((sa - 0.5, ylo), sb - sa + 1, yhi - ylo, color=col, alpha=0.28, lw=0, zorder=1))
        ax.text((sa + sb) / 2, yhi, state, ha="center", va="bottom", fontsize=8, weight="bold",
                color="#1a7a3a" if state in UP else "#2b6cb0")
    viz.candles(ax, seg, zorder=2)
    ax.set_xlim(-1, len(seg)); ax.set_ylim(ylo - (yhi - ylo) * 0.05, yhi + (yhi - ylo) * 0.12)
    ax.set_title(f"{title}   [{seg.index[0].date()}]", fontsize=10, loc="left")
    ax.tick_params(labelsize=6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--l2_sample", type=int, default=180)
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]
    insts = session_anchors(d5, 1_000_000)

    fig, ax = plt.subplots(3, 1, figsize=(15, 13))
    draw(ax[0], find_l3(d5, insts), "L3 (session blocks, 5m)")
    draw(ax[1], find_l1(d5, insts), "L1 (sessions, 5m)")
    draw(ax[2], find_l2(d5, d1, insts, args.l2_sample), "L2 (1m runs in a session)")
    fig.suptitle("Bullish continuation - UP leg -> CONSOLIDATION -> UP leg  (connected, per scale)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(ENGINE, "out", "continuation_examples.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
