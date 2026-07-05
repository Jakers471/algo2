"""experiments/engine/research/state_graphs.py — graphs of the states across scales.

Walks a window (default 6 months) at all three scales and renders a 6-panel PNG:

  1. state mix by scale (L1 / L2 / L3)
  2. impulses (L2) by session (Asia/London/NY)
  3. impulses (L2) by time of day (Chicago, 12h)
  4. what state comes immediately after an impulse
  5. when L3 is impulsive, how many impulses on the sub-scales (vs when it isn't)
  6. sub-impulses inside an L1-impulse session: up vs down

Read-only research VIEW; only calls the frozen engine. Heavier (1m + rolling grade),
so give it a couple minutes on 6 months.

  python experiments/engine/research/state_graphs.py
  python experiments/engine/research/state_graphs.py --start 2024-07-01
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
from anchors import session_anchors, rolling_states, meta_frame  # noqa: E402

SC = {"IMPULSE UP": "#1a9850", "IMPULSE DN": "#d73027", "GRIND UP": "#a7d8a0",
      "GRIND DN": "#f0a9a0", "CONSOLIDATION": "#5a8fd0", "WHIPSAW": "#b3b3b3", "UNCLEAR": "#e0e0e0"}
ORDER = ["IMPULSE UP", "IMPULSE DN", "GRIND UP", "GRIND DN", "CONSOLIDATION", "WHIPSAW"]


def scale_cuts(gs, ep=0.66, ap=0.50):
    return (float(np.quantile([g.efficiency for g in gs], ep)),
            float(np.quantile([g.acceptance for g in gs], ap)))


def reclassify(g, e, a):
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
    merged = []
    for a, b, s in raw:
        if merged and merged[-1][2] == s and a - merged[-1][1] - 1 <= gap:
            merged[-1][1] = b
        else:
            merged.append([a, b, s])
    return [(a, b, s) for a, b, s in merged if b - a + 1 >= min_len]


def h12(h):
    return f"{(h % 12) or 12}{'a' if h < 12 else 'p'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-07-01")
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= pd.Timestamp(args.start, tz="UTC")]
    insts = session_anchors(d5, 1_000_000)

    g1 = [grade(d5.iloc[s["start"]:s["end"] + 1]) for s in insts]
    e1, a1 = scale_cuts(g1)
    l1 = [reclassify(g, e1, a1) for g in g1]
    W = 8
    g3 = [grade(meta_frame(g1[i - W:i])) for i in range(W, len(g1))]
    e3, a3 = scale_cuts(g3)
    l3_by = {i: reclassify(g3[i - W], e3, a3) for i in range(W, len(g1))}

    cnt = {"L1": Counter(l1), "L3": Counter(l3_by.values()), "L2": Counter()}
    imp_sess = Counter(); imp_hour = Counter(); after = Counter()
    l3imp_l2, l3non_l2 = [], []
    l3imp_l1n = l3non_l1n = l3imp_ns = l3non_ns = 0
    within = {"IMPULSE UP": [0, 0], "IMPULSE DN": [0, 0]}
    within_n = {"IMPULSE UP": 0, "IMPULSE DN": 0}

    for i, s in enumerate(insts):
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 40:
            continue
        st = rolling_states(win1, 25)
        st_runs = runs(st)
        for state, _ra, _rb in st_runs:
            if state:
                cnt["L2"][state] += 1
        imps = merge_impulses(st)
        n_up = sum(1 for _a, _b, x in imps if x.endswith("UP"))
        n_dn = len(imps) - n_up
        for a, b, _x in imps:
            imp_sess[s["session"]] += 1
            imp_hour[win1.index[a].tz_convert("America/Chicago").hour] += 1
            nxt = next((state for state, ra, _rb in st_runs if ra > b), None)
            if nxt:
                after[nxt] += 1
        l3s = l3_by.get(i)
        if l3s:
            if l3s.startswith("IMPULSE"):
                l3imp_l2.append(len(imps)); l3imp_ns += 1; l3imp_l1n += l1[i].startswith("IMPULSE")
            else:
                l3non_l2.append(len(imps)); l3non_ns += 1; l3non_l1n += l1[i].startswith("IMPULSE")
        if l1[i] in within:
            within[l1[i]][0] += n_up; within[l1[i]][1] += n_dn; within_n[l1[i]] += 1

    # ---- plot ----
    fig, ax = plt.subplots(2, 3, figsize=(19, 10))
    fig.suptitle(f"Engine states across scales - NQ  {d5.index[0].date()} to {d5.index[-1].date()}", fontsize=13)

    # 1 state mix by scale
    a0 = ax[0, 0]; x = np.arange(len(ORDER)); w = 0.26
    for k, sc in enumerate(("L1", "L2", "L3")):
        tot = sum(cnt[sc].values()) or 1
        a0.bar(x + (k - 1) * w, [cnt[sc].get(s, 0) / tot for s in ORDER], w, label=sc)
    a0.set_xticks(x); a0.set_xticklabels([s.replace(" ", "\n") for s in ORDER], fontsize=7)
    a0.set_title("1. state mix by scale (share of scale)"); a0.legend(fontsize=8); a0.set_ylabel("fraction")

    # 2 impulses by session
    a1 = ax[0, 1]; order_s = ["Asia", "London", "NY"]
    a1.bar(order_s, [imp_sess.get(s, 0) for s in order_s], color="#1a9850")
    a1.set_title("2. L2 impulses by session"); a1.set_ylabel("# impulses")

    # 3 impulses by hour (chicago)
    a2 = ax[0, 2]; hrs = sorted(imp_hour)
    a2.bar([h12(h) for h in hrs], [imp_hour[h] for h in hrs], color="#5a8fd0")
    a2.set_title("3. L2 impulses by time of day (Chicago)"); a2.tick_params(axis="x", rotation=60, labelsize=7)

    # 4 what's after an impulse
    a3 = ax[1, 0]; keys = [s for s in ORDER + ["UNCLEAR"] if after.get(s)]; tot4 = sum(after.values()) or 1
    a3.bar([k.replace(" ", "\n") for k in keys], [after[k] / tot4 for k in keys], color=[SC.get(k) for k in keys])
    a3.set_title("4. state right AFTER an impulse"); a3.tick_params(axis="x", labelsize=7); a3.set_ylabel("fraction")

    # 5 L3 impulsive -> sub-scale impulses
    a4 = ax[1, 1]
    l2i = np.mean(l3imp_l2) if l3imp_l2 else 0
    l2n = np.mean(l3non_l2) if l3non_l2 else 0
    l1i = l3imp_l1n / l3imp_ns if l3imp_ns else 0
    l1n = l3non_l1n / l3non_ns if l3non_ns else 0
    a4.bar(["L3 impulsive", "L3 not"], [l2i, l2n], color="#1a9850")
    a4.set_title("5. L2 impulses/session by L3 state"); a4.set_ylabel("avg L2 impulses/session")
    a4.text(0, l2i, f" L1 impulse rate {l1i:.0%}", ha="center", va="bottom", fontsize=8)
    a4.text(1, l2n, f" {l1n:.0%}", ha="center", va="bottom", fontsize=8)

    # 6 sub-impulses inside an L1-impulse session
    a5 = ax[1, 2]; xx = np.arange(2)
    ups = [within["IMPULSE UP"][0] / max(1, within_n["IMPULSE UP"]), within["IMPULSE DN"][0] / max(1, within_n["IMPULSE DN"])]
    dns = [within["IMPULSE UP"][1] / max(1, within_n["IMPULSE UP"]), within["IMPULSE DN"][1] / max(1, within_n["IMPULSE DN"])]
    a5.bar(xx - 0.18, ups, 0.36, label="up sub-impulses", color="#1a9850")
    a5.bar(xx + 0.18, dns, 0.36, label="down sub-impulses", color="#d73027")
    a5.set_xticks(xx); a5.set_xticklabels([f"in IMPULSE UP\n({within_n['IMPULSE UP']} sess)",
                                           f"in IMPULSE DN\n({within_n['IMPULSE DN']} sess)"], fontsize=8)
    a5.set_title("6. sub-impulses inside an L1 impulse"); a5.legend(fontsize=8); a5.set_ylabel("avg per session")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(ENGINE, "out", "state_graphs.png")
    fig.savefig(out, dpi=110)
    print("wrote", out, "|", sum(imp_sess.values()), "impulses over", len(insts), "sessions")


if __name__ == "__main__":
    main()
