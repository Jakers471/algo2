"""experiments/engine/engine_stats.py — large-scale research on the engine's states.

The `break_sequence` idea, upgraded: run grade() over years of data and study the
SEQUENCE of rich states at three scales.

  L1 (session, 5m)         : state mix, what-follows-what, how long regimes last.
  L3 (8-session meta, 5m)  : same, at the coarse scale.
  cross-scale (L1 - L2)    : what impulses (1m) fill each session state — the fractal
                             test (does a CONSOLIDATION session hold cancelling impulses?).

SCALE-RELATIVE CUTS: grade()'s absolute IMPULSE/etc. thresholds are tuned for the fine
(impulse) scale, so whole sessions almost always read WHIPSAW. Since grade() also
returns the raw `efficiency` / `acceptance`, this research layer re-classifies each
unit against ITS OWN scale's distribution ("directional" = top-third efficiency among
sessions, etc.). The frozen core is untouched — we only re-threshold here.

Read-only research VIEW; only calls the frozen engine.

  python experiments/engine/engine_stats.py
  python experiments/engine/engine_stats.py --start 2020-01-01 --sample 150 --eff_pct 0.66
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import session_anchors, impulse_anchors, meta_frame  # noqa: E402


def scale_cuts(grades, eff_pct, acc_pct):
    """Percentile thresholds from THIS scale's own grade distribution."""
    e = float(np.quantile([g.efficiency for g in grades], eff_pct))
    a = float(np.quantile([g.acceptance for g in grades], acc_pct))
    return e, a


def reclassify(g, e_cut, a_cut):
    """State from raw efficiency/acceptance using scale-relative cuts."""
    d = "UP" if g.direction == "bull" else "DN"
    if g.efficiency >= e_cut:
        return ("GRIND " if g.acceptance >= a_cut else "IMPULSE ") + d
    return "CONSOLIDATION" if g.acceptance >= a_cut else "WHIPSAW"


def runs(seq):
    out, i = [], 0
    while i < len(seq):
        j = i
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        out.append((seq[i], j - i)); i = j
    return out


def mix(states, title):
    c = Counter(states); n = len(states)
    print(f"\n{title}  ({n})")
    for s, k in c.most_common():
        print(f"  {s:<14} {k/n:>4.0%}  {'#' * round(k/n*40)}")


def follows(states, title):
    print(f"\n{title}")
    nxt = defaultdict(Counter)
    for a, b in zip(states, states[1:]):
        nxt[a][b] += 1
    for a, _ in Counter(states).most_common():
        tot = sum(nxt[a].values())
        if not tot:
            continue
        top = "  |  ".join(f"{b} {k/tot:.0%}" for b, k in nxt[a].most_common(3))
        print(f"  after {a:<14} -> {top}   (n={tot})")


def runlengths(states, title):
    print(f"\n{title}")
    by = defaultdict(list)
    for s, ln in runs(states):
        by[s].append(ln)
    for s, lens in sorted(by.items(), key=lambda kv: -sum(kv[1])):
        print(f"  {s:<14} avg {sum(lens)/len(lens):.1f}   longest {max(lens)}   ({len(lens)} runs)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--sample", type=int, default=120, help="sessions for the 1m cross-scale pass")
    ap.add_argument("--eff_pct", type=float, default=0.66, help="efficiency percentile = directional")
    ap.add_argument("--acc_pct", type=float, default=0.50, help="acceptance percentile = accepted")
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)

    print("=" * 62)
    print(f"  ENGINE STATS - NQ sessions since {args.start}   (scale-relative cuts)")
    print("=" * 62)

    # --- L1: grade every session, re-classify against the session-scale distribution ---
    g1 = [grade(d5.iloc[s["start"]:s["end"] + 1]) for s in spans]
    e1, a1 = scale_cuts(g1, args.eff_pct, args.acc_pct)
    l1 = [reclassify(g, e1, a1) for g in g1]
    print(f"\nL1 cuts: directional if efficiency >= {e1:.3f} (top {1-args.eff_pct:.0%}), "
          f"accepted if acceptance >= {a1:.2f}")
    mix(l1, "L1 SESSION STATE MIX")
    follows(l1, "WHAT FOLLOWS WHAT (session -> next session)")
    runlengths(l1, "HOW LONG REGIMES LAST (session runs)")

    # --- L3: rolling 8-session meta-candle grade, re-classified at that scale ---
    W = 8
    g3 = [grade(meta_frame(g1[i - W:i])) for i in range(W, len(g1))]
    e3, a3 = scale_cuts(g3, args.eff_pct, args.acc_pct)
    l3 = [reclassify(g, e3, a3) for g in g3]
    print(f"\nL3 cuts: directional if efficiency >= {e3:.3f}, accepted if acceptance >= {a3:.2f}")
    mix(l3, f"L3 STATE MIX ({W}-session meta-candles)")
    follows(l3, "WHAT FOLLOWS WHAT (L3 -> next L3)")

    # --- cross-scale: what impulses (1m) fill each session state (scale-relative L1) ---
    sample = spans[-args.sample:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[sample[0]["start"]]]
    co = defaultdict(Counter); sess = Counter()
    for s in sample:
        win5 = d5.iloc[s["start"]:s["end"] + 1]
        st = reclassify(grade(win5), e1, a1)
        win1 = d1.loc[win5.index[0]:win5.index[-1] + pd.Timedelta("5min")].reset_index(drop=True)
        if len(win1) < 40:
            continue
        sess[st] += 1
        for a in impulse_anchors(win1):
            co[st][a["state"]] += 1

    print(f"\nCROSS-SCALE - impulses (1m) inside each session state  (sample {sum(sess.values())} sessions)")
    for st, n in sess.most_common():
        up = co[st].get("IMPULSE UP", 0) / n
        dn = co[st].get("IMPULSE DN", 0) / n
        tilt = "up-dominant" if up > dn * 1.3 else "down-dominant" if dn > up * 1.3 else "balanced -> cancels"
        print(f"  {st:<14} per session: {up:.1f} up-impulse / {dn:.1f} down-impulse   ({tilt})")


if __name__ == "__main__":
    main()
