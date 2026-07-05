"""experiments/engine/research/state_examples.py — WHIPSAW vs CONSOLIDATION, all 3 scales.

Both states "go nowhere" (low progress) — the difference is ACCEPTANCE (volume):
  CONSOLIDATION = fat POC, price coiled at a level (organized rest).
  WHIPSAW       = spread volume, price thrashing with no clean level (noise).

Finds a real low-progress example of each at each scale and shows candles + the volume
profile (the profile is where the difference is obvious):
  L3 = an 8-session span (5m) · L1 = one session (5m) · L2 = a 1m segment inside a session.

Read-only research VIEW; only calls the frozen engine.

  python experiments/engine/research/state_examples.py
"""
import argparse
import os
import sys

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
import viz  # noqa: E402


def pick(cands):
    """cands: [(win, grade)]. Among low-progress ones, return (whipsaw, consolidation)
    = (lowest acceptance, highest acceptance)."""
    med = float(np.median([g.efficiency for _w, g in cands]))
    low = [(w, g) for w, g in cands if g.efficiency <= med and g.range > 0]
    whip = min(low, key=lambda c: c[1].acceptance)
    cons = max(low, key=lambda c: c[1].acceptance)
    return whip, cons


def pick_impulse(cands):
    """Among high-progress candidates, the cleanest UP and DOWN thrusts (max efficiency)."""
    med = float(np.median([g.efficiency for _w, g in cands]))
    high = [(w, g) for w, g in cands if g.efficiency >= med and g.range > 0]
    up = max([c for c in high if c[1].direction == "bull"], key=lambda c: c[1].efficiency)
    dn = max([c for c in high if c[1].direction == "bear"], key=lambda c: c[1].efficiency)
    return up, dn


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


def cell(ax, win, g, label):
    pw = max(8, len(win) * 0.13)
    viz.volume_profile(ax, win, g, pw)
    viz.candles(ax, win)
    ax.set_xlim(-pw - 3, len(win) + 2)
    ax.set_title(f"{label}   eff {g.efficiency:.2f} · acc {g.acceptance:.2f}   "
                 f"(range {g.range:.0f}, {len(win)} bars)", fontsize=9, loc="left")
    ax.tick_params(labelsize=6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-09-01")
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]
    insts = session_anchors(d5, 1_000_000)

    # L1: each session (5m)
    l1c = [(d5.iloc[s["start"]:s["end"] + 1], grade(d5.iloc[s["start"]:s["end"] + 1])) for s in insts]
    l1c = [c for c in l1c if len(c[0]) > 20]

    # L3: sliding 8-session span (5m)
    l3c = []
    for i in range(8, len(insts), 2):
        span = d5.iloc[insts[i - 8]["start"]:insts[i - 1]["end"] + 1]
        if len(span) > 100:
            l3c.append((span, grade(span)))

    # L2: 1m consolidation / whipsaw runs inside a sample of sessions
    l2c = []
    for s in insts[-45:]:
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 40:
            continue
        st = rolling_states(win1, 25)
        i = 0
        while i < len(st):
            j = i
            while j < len(st) and st[j] == st[i]:
                j += 1
            if st[i] in ("CONSOLIDATION", "WHIPSAW") and j - i >= 25:
                seg = win1.iloc[i:j]
                l2c.append((seg, grade(seg)))
            i = j
        for a, b, _x in merge_impulses(st):       # also collect impulse runs
            if b - a + 1 >= 12:
                l2c.append((win1.iloc[a:b + 1], grade(win1.iloc[a:b + 1])))

    scales = [("L3  (8-session span, 5m)", pick(l3c)),
              ("L1  (one session, 5m)", pick(l1c)),
              ("L2  (1m segment)", pick(l2c))]

    fig, ax = plt.subplots(3, 2, figsize=(16, 12))
    for r, (name, (whip, cons)) in enumerate(scales):
        cell(ax[r, 0], whip[0], whip[1], f"{name}  —  WHIPSAW")
        cell(ax[r, 1], cons[0], cons[1], f"{name}  —  CONSOLIDATION")
    fig.suptitle("WHIPSAW vs CONSOLIDATION across scales - both go nowhere; the PROFILE tells them apart "
                 "(spread vs fat POC)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(ENGINE, "out", "state_examples.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)

    # --- IMPULSE UP vs IMPULSE DOWN ---
    imp = [("L3  (8-session span, 5m)", pick_impulse(l3c)),
           ("L1  (one session, 5m)", pick_impulse(l1c)),
           ("L2  (1m segment)", pick_impulse(l2c))]
    fig2, ax2 = plt.subplots(3, 2, figsize=(16, 12))
    for r, (name, (up, dn)) in enumerate(imp):
        cell(ax2[r, 0], up[0], up[1], f"{name}  -  IMPULSE UP")
        cell(ax2[r, 1], dn[0], dn[1], f"{name}  -  IMPULSE DOWN")
    fig2.suptitle("IMPULSE UP vs IMPULSE DOWN across scales - clean directional thrusts "
                  "(high efficiency; volume spread through the move, no fat POC)", fontsize=12)
    fig2.tight_layout(rect=[0, 0, 1, 0.97])
    out2 = os.path.join(ENGINE, "out", "impulse_examples.png")
    fig2.savefig(out2, dpi=110)
    print("wrote", out2)


if __name__ == "__main__":
    main()
