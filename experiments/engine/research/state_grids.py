"""experiments/engine/research/state_grids.py — 3 examples per condition, per scale.

One PNG per scale (L1 / L2 / L3). Each = the 6 states down the rows, 3 real examples
across the columns, with each example's volume profile (the profile is the tell).

States are picked by the two axes (efficiency = progress, acceptance = volume
concentration), split at the scale's own median:
  IMPULSE ↑/↓  = high eff, low acc, directional      GRIND ↑/↓ = high eff, high acc
  WHIPSAW      = low eff, low acc                     CONSOLIDATION = low eff, high acc

Read-only research VIEW; only calls the frozen engine.

  python experiments/engine/research/state_grids.py
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


def cell(a, win, g):
    pw = max(6, len(win) * 0.13)
    viz.volume_profile(a, win, g, pw)
    viz.candles(a, win)
    a.set_xlim(-pw - 3, len(win) + 2)
    a.set_title(f"eff {g.efficiency:.2f}  acc {g.acceptance:.2f}  ({len(win)}b)", fontsize=7)
    a.tick_params(labelsize=5)


def build_grid(name, pool, out):
    me = float(np.median([g.efficiency for _w, g in pool]))
    ma = float(np.median([g.acceptance for _w, g in pool]))
    hi_eff = lambda g: g.efficiency >= me
    hi_acc = lambda g: g.acceptance >= ma
    conds = [
        ("IMPULSE UP", lambda g: hi_eff(g) and not hi_acc(g) and g.direction == "bull", lambda c: -c[1].efficiency),
        ("IMPULSE DOWN", lambda g: hi_eff(g) and not hi_acc(g) and g.direction == "bear", lambda c: -c[1].efficiency),
        ("GRIND UP", lambda g: hi_eff(g) and hi_acc(g) and g.direction == "bull", lambda c: -c[1].efficiency),
        ("GRIND DOWN", lambda g: hi_eff(g) and hi_acc(g) and g.direction == "bear", lambda c: -c[1].efficiency),
        ("CONSOLIDATION", lambda g: not hi_eff(g) and hi_acc(g), lambda c: -c[1].acceptance),
        ("WHIPSAW", lambda g: not hi_eff(g) and not hi_acc(g), lambda c: c[1].acceptance),
    ]
    fig, ax = plt.subplots(6, 3, figsize=(15, 18))
    for row, (cond, filt, keyf) in enumerate(conds):
        picks = sorted([c for c in pool if c[1].range > 0 and filt(c[1])], key=keyf)[:3]
        for col in range(3):
            a = ax[row][col]
            if col < len(picks):
                cell(a, *picks[col])
            else:
                a.axis("off")
        ax[row][0].set_ylabel(cond, fontsize=11, fontweight="bold", labelpad=10)
    fig.suptitle(f"{name} - 3 examples per condition  (rows = states, each with its volume profile)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(out, dpi=105)
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-06-01")
    ap.add_argument("--l2_sessions", type=int, default=70)
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]
    insts = session_anchors(d5, 1_000_000)

    # L1 pool: every session
    l1 = [(d5.iloc[s["start"]:s["end"] + 1], grade(d5.iloc[s["start"]:s["end"] + 1])) for s in insts]
    l1 = [c for c in l1 if len(c[0]) > 20]

    # L3 pool: sliding 8-session spans
    l3 = []
    for i in range(8, len(insts), 2):
        span = d5.iloc[insts[i - 8]["start"]:insts[i - 1]["end"] + 1]
        if len(span) > 100:
            l3.append((span, grade(span)))

    # L2 pool: runs + impulses inside a sample of sessions
    l2 = []
    for s in insts[-args.l2_sessions:]:
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 40:
            continue
        st = rolling_states(win1, 25)
        i = 0
        while i < len(st):
            j = i
            while j < len(st) and st[j] == st[i]:
                j += 1
            if j - i >= 20:
                l2.append((win1.iloc[i:j], grade(win1.iloc[i:j])))
            i = j
        for a, b, _x in merge_impulses(st):
            if b - a + 1 >= 12:
                l2.append((win1.iloc[a:b + 1], grade(win1.iloc[a:b + 1])))

    build_grid("L1 (session, 5m)", l1, os.path.join(ENGINE, "out", "state_grid_L1.png"))
    build_grid("L2 (1m segment)", l2, os.path.join(ENGINE, "out", "state_grid_L2.png"))
    build_grid("L3 (8-session span, 5m)", l3, os.path.join(ENGINE, "out", "state_grid_L3.png"))


if __name__ == "__main__":
    main()
