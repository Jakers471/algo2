"""experiments/engine/impulse_sequence.py — L2: the impulse EVENT stream.

The most direct descendant of the archived break_sequence.py: impulses ARE the "breaks."
Detects every impulse (1m, inside each session) in time order and asks:

  - DIRECTION: what comes next after an up/down impulse (continuation vs reversal)?
  - STREAKS: how long do same-direction impulse runs go?
  - BETWEEN: what state sits between two impulses (consolidation = accumulation, or
    whipsaw)?
  - BIRTH: do impulses born out of a CONSOLIDATION run bigger than ones out of WHIPSAW?

Heavier than the L1/L3 stats (needs 1m + rolling grade per session), so it runs on a
sample of recent sessions. Read-only research VIEW; only calls the frozen engine.

  python experiments/engine/impulse_sequence.py
  python experiments/engine/impulse_sequence.py --sessions 400
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)                       # engine/ (frozen core + helpers)
REPO = os.path.dirname(os.path.dirname(ENGINE))      # repo root
sys.path.insert(0, ENGINE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import session_anchors, impulse_anchors  # noqa: E402


def runs(seq):
    out, i = [], 0
    while i < len(seq):
        j = i
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        out.append((seq[i], j - i)); i = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--sessions", type=int, default=300, help="recent sessions to scan (1m; heavier)")
    args = ap.parse_args()

    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)[-args.sessions:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[spans[0]["start"]]]

    dseq = []            # direction stream (UP/DN) across all impulses, time order
    sizes_by_gap = defaultdict(list)   # preceding-gap family -> [impulse |net|]
    between = Counter()  # state of the gap between two impulses
    for s in spans:
        win5 = d5.iloc[s["start"]:s["end"] + 1]
        win1 = d1.loc[win5.index[0]:win5.index[-1] + pd.Timedelta("5min")].reset_index(drop=True)
        if len(win1) < 40:
            continue
        c = win1["close"].to_numpy(float)
        prev_end = None
        for a in impulse_anchors(win1):
            gap_fam = "first (no gap)"
            if prev_end is not None:
                gap = win1.iloc[prev_end + 1:a["start"]]
                if len(gap) >= 8:
                    gs = grade(gap).state
                    between[gs] += 1
                    gap_fam = "after CONSOLIDATION" if gs == "CONSOLIDATION" else \
                              "after WHIPSAW" if gs == "WHIPSAW" else "after " + gs
            dseq.append("UP" if a["state"].endswith("UP") else "DN")
            sizes_by_gap[gap_fam].append(abs(float(c[a["end"]] - c[a["start"]])))
            prev_end = a["end"]

    m = len(dseq)
    nu = dseq.count("UP")
    print("=" * 60)
    print(f"  L2 IMPULSE SEQUENCE - NQ, last {len(spans)} sessions (1m)")
    print(f"  {m} impulses:  {nu} up ({nu/m:.0%})   {m-nu} down ({(m-nu)/m:.0%})")
    print("=" * 60)

    print("\nWHAT COMES NEXT (impulse -> next impulse):")
    nxt = defaultdict(Counter)
    for a, b in zip(dseq, dseq[1:]):
        nxt[a][b] += 1
    for d in ("UP", "DN"):
        tot = sum(nxt[d].values())
        same = nxt[d][d]
        print(f"  after an {d} impulse -> {d} {same/tot:.0%}  /  {'DN' if d=='UP' else 'UP'} "
              f"{(tot-same)/tot:.0%}   (n={tot})")

    print("\nSTREAKS (same-direction impulses in a row):")
    for d in ("UP", "DN"):
        lens = [ln for v, ln in runs(dseq) if v == d]
        if not lens:
            continue
        ge2 = sum(1 for x in lens if x >= 2)
        print(f"  {d}: {len(lens)} streaks, longest {max(lens)}, "
              f"{ge2/len(lens):.0%} reach 2+  (after 1 {d}, {ge2/len(lens):.0%} chance of another)")

    print("\nBETWEEN TWO IMPULSES, price is in:")
    tb = sum(between.values()) or 1
    for st, k in between.most_common():
        print(f"  {st:<14} {k/tb:>4.0%}")

    print("\nDO IMPULSES BORN OUT OF CONSOLIDATION RUN BIGGER?  (avg |move| in pts)")
    for fam in ["after CONSOLIDATION", "after WHIPSAW", "first (no gap)"]:
        v = sizes_by_gap.get(fam, [])
        if v:
            print(f"  {fam:<22} {sum(v)/len(v):>6.0f} pts   (n={len(v)})")
    for fam, v in sizes_by_gap.items():
        if fam not in ("after CONSOLIDATION", "after WHIPSAW", "first (no gap)") and v:
            print(f"  {fam:<22} {sum(v)/len(v):>6.0f} pts   (n={len(v)})")


if __name__ == "__main__":
    main()
