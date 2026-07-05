"""experiments/engine/research/sequence_patterns.py — impulse -> pause -> ?

Goes beyond "what follows an impulse" to the 3-step pattern you care about:
  IMPULSE -> (CONSOLIDATION or WHIPSAW pause) -> next IMPULSE   (continue vs reverse?)

The key trading question: does a CLEAN pause (consolidation) lead to continuation more
than a NOISY pause (whipsaw)? Split by bull/bear. Also lists the most common 3-step
sequences. L2 impulse events on 1m; read-only, calls the frozen engine.

  python experiments/engine/research/sequence_patterns.py
  python experiments/engine/research/sequence_patterns.py --sessions 400
"""
import argparse
import os
import sys
from collections import Counter

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
from anchors import session_anchors, rolling_states  # noqa: E402


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--sessions", type=int, default=300)
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)[-args.sessions:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[spans[0]["start"]]]

    tri = Counter()                 # (prev_dir, gap_family, next_dir)
    for s in spans:
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 40:
            continue
        st = rolling_states(win1, 25)
        imps = merge_impulses(st)
        for k in range(1, len(imps)):
            pa, pb, px = imps[k - 1]
            ca, cb, cx = imps[k]
            pdir = "UP" if px.endswith("UP") else "DN"
            cdir = "UP" if cx.endswith("UP") else "DN"
            gap = win1.iloc[pb + 1:ca]
            if len(gap) < 8:
                fam = "tiny gap"
            else:
                gs = grade(gap).state
                fam = gs if gs in ("CONSOLIDATION", "WHIPSAW") else "counter-move"
            tri[(pdir, fam, cdir)] += 1

    def cont(pdir, fam):
        c = tri[(pdir, fam, pdir)]
        r = tri[(pdir, fam, "DN" if pdir == "UP" else "UP")]
        return c, r, (c / (c + r) if c + r else 0)

    print("=" * 62)
    print(f"  IMPULSE -> PAUSE -> ? (does the trend continue after a pause?)")
    print(f"  NQ, last {len(spans)} sessions, 1m")
    print("=" * 62)
    for pdir in ("UP", "DN"):
        print(f"\n  after an {pdir} impulse, then a ...")
        for fam in ("CONSOLIDATION", "WHIPSAW"):
            c, r, p = cont(pdir, fam)
            print(f"    {fam:<14} -> {pdir} {p:.0%} continue  /  {'reverse':<7} {1-p:.0%}   (n={c+r})")

    print("\n  TOP 3-STEP SEQUENCES (impulse, pause, impulse):")
    for (a, f, b), k in tri.most_common(8):
        print(f"    {a:<3} -> {f:<14} -> {b:<3}   {k}")

    # graph: continuation odds by direction x pause type
    fig, ax = plt.subplots(figsize=(9, 5.5))
    cats = [("UP", "CONSOLIDATION"), ("UP", "WHIPSAW"), ("DN", "CONSOLIDATION"), ("DN", "WHIPSAW")]
    labels = ["UP after\nCONSOLIDATION", "UP after\nWHIPSAW", "DN after\nCONSOLIDATION", "DN after\nWHIPSAW"]
    vals = [cont(d, f)[2] for d, f in cats]
    ns = [sum(cont(d, f)[:2]) for d, f in cats]
    colors = ["#1a9850", "#7fc97f", "#d73027", "#f2a6a0"]
    b = ax.bar(labels, vals, color=colors)
    for bar, v, n in zip(b, vals, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0%}\n(n={n})", ha="center", va="bottom", fontsize=9)
    ax.axhline(0.5, color="#888", ls="--", lw=0.8)
    ax.set_ylim(0, 1); ax.set_ylabel("chance the trend CONTINUES (next impulse same direction)")
    ax.set_title(f"Does an impulse continue after a pause?  (NQ, {len(spans)} sessions, 1m)\n"
                 "above the dashed line = continuation edge", fontsize=11)
    fig.tight_layout()
    out = os.path.join(ENGINE, "out", "sequence_patterns.png")
    fig.savefig(out, dpi=110)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
