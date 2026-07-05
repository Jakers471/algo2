"""experiments/engine/cascade_examples.py — 3 more cascades on different data.

Same engine, same descent as cascade.py, pointed at three different windows so you see
the fractal read on varied structure. Scans for windows that descend THREE distinct
levels (a clean sub-impulse at each step), one from each third of the data for variety.

  python experiments/engine/cascade_examples.py
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from cascade import panel, biggest_impulse  # noqa: E402 (reuse the exact cascade drawing)
from anchors import session_anchors  # noqa: E402


def descent(d5, d1, sel):
    """-> (A, cA, B, cB, C) only if it descends 3 distinct levels, else None."""
    A = d5.iloc[sel[0]["start"]:sel[-1]["end"] + 1]
    cA = biggest_impulse(A)
    if cA is None:
        return None
    B = d1.loc[A.index[cA["start"]]:A.index[cA["end"]]]
    if len(B) < 40:
        return None
    cB = biggest_impulse(B)
    if cB is None:                      # no clean 3rd level -> reject
        return None
    C = d1.loc[B.index[cB["start"]]:B.index[cB["end"]]]
    if len(C) < 6:
        return None
    return A, cA, B, cB, C


def render(desc, out, tag):
    A, cA, B, cB, C = desc
    d0 = str(A.index[0].date())
    fig, axes = plt.subplots(3, 1, figsize=(15, 13))
    panel(axes[0], A, f"(1) WIDEST  -  5 sessions on 5m  [{d0}]", child=cA)
    panel(axes[1], B, "(2) ZOOM into the box above  -  1m", child=cB)
    panel(axes[2], C, "(3) ZOOM into the box above  -  1m")
    fig.suptitle(f"Engine cascade - {tag}  ({d0}): same grade() at every zoom", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(out, dpi=110)
    print("wrote", out, "-", A.index[0].date())


def main():
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    spans = session_anchors(d5, 1_000_000)
    n = len(spans)
    third = n // 3
    regions = [(2, third), (third, 2 * third), (2 * third, n - 6)]
    k = 1
    for lo, hi in regions:
        i = lo
        while i < hi - 5:
            desc = descent(d5, d1, spans[i:i + 5])
            if desc:
                render(desc, os.path.join(HERE, "out", f"cascade_ex{k}.png"), f"example {k}")
                k += 1
                break
            i += 3


if __name__ == "__main__":
    main()
