"""experiments/engine/research/alignment.py — do the scales line up?

Measures cross-scale directional alignment: when the higher scale points UP, does the
lower scale point UP inside it (nesting/confluence), or do they diverge?

  L3->L1 : for each L3 direction, what direction are the L1 sessions inside it?
  L1->L2 : for each L1 direction, which way do the 1m impulses inside tilt?
  full stack : how often do all three point the same directional way at once?

Direction of a state: UP = impulse/grind up | DN = impulse/grind down | FLAT = consol/whip.
Read-only research VIEW; only calls the frozen engine.

  python experiments/engine/research/alignment.py
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ENGINE))
sys.path.insert(0, ENGINE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import session_anchors, rolling_states, meta_frame  # noqa: E402

COL = {"UP": "#1a9850", "FLAT": "#b3b3b3", "DN": "#d73027"}


def cuts(gs, ep=0.66, ap=0.50):
    return (float(np.quantile([g.efficiency for g in gs], ep)),
            float(np.quantile([g.acceptance for g in gs], ap)))


def reclass(g, e, a):
    d = "UP" if g.direction == "bull" else "DN"
    if g.efficiency >= e:
        return ("GRIND " if g.acceptance >= a else "IMPULSE ") + d
    return "CONSOLIDATION" if g.acceptance >= a else "WHIPSAW"


def dir_of(s):
    if s in ("IMPULSE UP", "GRIND UP"):
        return "UP"
    if s in ("IMPULSE DN", "GRIND DN"):
        return "DN"
    return "FLAT"


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


def stacked(ax, buckets, title, xlabel):
    conds = ["UP", "FLAT", "DN"]
    bottom = np.zeros(len(conds))
    for oc in ("UP", "FLAT", "DN"):
        vals = [buckets[c].get(oc, 0) / max(1, sum(buckets[c].values())) for c in conds]
        ax.bar([f"{xlabel}\n{c}" for c in conds], vals, bottom=bottom, color=COL[oc], label=oc)
        for xi, (v, b0) in enumerate(zip(vals, bottom)):
            if v > 0.06:
                ax.text(xi, b0 + v / 2, f"{v:.0%}", ha="center", va="center", fontsize=8, color="white")
        bottom += np.array(vals)
    ns = [sum(buckets[c].values()) for c in conds]
    for xi, n in enumerate(ns):
        ax.text(xi, 1.01, f"n={n}", ha="center", fontsize=7, color="#555")
    ax.set_ylim(0, 1.06); ax.set_title(title, fontsize=11); ax.legend(fontsize=8, loc="lower right")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--sample", type=int, default=200, help="sessions for the 1m L1->L2 pass")
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    insts = session_anchors(d5, 1_000_000)

    g1 = [grade(d5.iloc[s["start"]:s["end"] + 1]) for s in insts]
    e1, a1 = cuts(g1)
    l1 = [reclass(g, e1, a1) for g in g1]
    W = 8
    g3 = [grade(meta_frame(g1[i - W:i])) for i in range(W, len(g1))]
    e3, a3 = cuts(g3)
    l3 = {i: reclass(g3[i - W], e3, a3) for i in range(W, len(g1))}

    # L3 -> L1 (full window)
    l3_l1 = defaultdict(Counter)
    for i in range(W, len(insts)):
        l3_l1[dir_of(l3[i])][dir_of(l1[i])] += 1

    # L1 -> L2 (sample, 1m) + full stack
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    sample_ix = list(range(max(W, len(insts) - args.sample), len(insts)))
    d1 = d1.loc[d1.index >= d5.index[insts[sample_ix[0]]["start"]]]
    l1_l2 = defaultdict(Counter)
    stack_agree = stack_dir = 0
    for i in sample_ix:
        s = insts[i]
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 40:
            continue
        imps = merge_impulses(rolling_states(win1, 25))
        up = sum(1 for _a, _b, x in imps if x.endswith("UP"))
        dn = len(imps) - up
        l2d = "UP" if up > dn * 1.3 else "DN" if dn > up * 1.3 else "FLAT"
        l1_l2[dir_of(l1[i])][l2d] += 1
        if dir_of(l3.get(i, "FLAT")) in ("UP", "DN"):
            stack_dir += 1
            if dir_of(l3[i]) == dir_of(l1[i]) == l2d:
                stack_agree += 1

    print("=" * 58)
    print(f"  CROSS-SCALE ALIGNMENT - NQ since {args.start} ({len(insts)} sessions)")
    print("=" * 58)
    print("\n  L3 -> L1 : when the multi-session scale is directional, does the session follow?")
    for d in ("UP", "DN"):
        b = l3_l1[d]; t = sum(b.values())
        print(f"    L3 {d}: L1 same {b[d]/t:.0%} | flat {b['FLAT']/t:.0%} | opposite {b['DN' if d=='UP' else 'UP']/t:.0%}  (n={t})")
    print("\n  L1 -> L2 : when the session is directional, do the 1m impulses tilt with it?")
    for d in ("UP", "DN"):
        b = l1_l2[d]; t = sum(b.values()) or 1
        print(f"    L1 {d}: L2 same {b[d]/t:.0%} | flat {b['FLAT']/t:.0%} | opposite {b['DN' if d=='UP' else 'UP']/t:.0%}  (n={sum(b.values())})")
    print(f"\n  FULL STACK: all three agree on direction {stack_agree/max(1,stack_dir):.0%} "
          f"of directional moments (n={stack_dir})")

    fig, ax = plt.subplots(1, 2, figsize=(13, 6))
    stacked(ax[0], l3_l1, "L3 -> L1  (session direction, given L3)", "L3")
    stacked(ax[1], l1_l2, "L1 -> L2  (1m impulse tilt, given L1)", "L1")
    fig.suptitle("Cross-scale alignment - does the lower scale point the same way as the higher?", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(ENGINE, "out", "alignment.png")
    fig.savefig(out, dpi=110)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
