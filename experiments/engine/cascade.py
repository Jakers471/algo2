"""experiments/engine/cascade.py — the fractal descent (price within price within price).

Three panels, top->down, SAME drill-down format (candles + impulse boxes + volume
profile + full grade). Each panel is a zoomed-in piece of the one above — the parent
boxes (purple) the child region and says "zoom", so it's obvious where each layer
comes from in the layer above:

  (1) widest   : several sessions (5m)      -> box its biggest impulse
  (2) zoom     : that impulse on 1m         -> box its biggest sub-impulse
  (3) zoom     : that sub-impulse on 1m

Same grade() at every panel — that's the whole point.

  python experiments/engine/cascade.py
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import impulse_anchors, session_anchors  # noqa: E402
import viz  # noqa: E402

HL = "#7a2fd0"   # highlight color for the child region


def biggest_impulse(win):
    imps = impulse_anchors(win)
    if not imps:
        return None
    c = win["close"].to_numpy(float)
    return max(imps, key=lambda a: abs(c[a["end"]] - c[a["start"]]))


def panel(ax, win, title, child=None):
    g = grade(win)
    ylo, yhi = float(win["low"].min()), float(win["high"].max())
    pw = max(8, len(win) * 0.12)
    viz.impulse_boxes(ax, impulse_anchors(win), ylo, yhi)
    viz.volume_profile(ax, win, g, pw)
    viz.candles(ax, win)
    viz.grade_textbox(ax, g)
    if child is not None:
        ax.add_patch(Rectangle((child["start"] - 0.5, ylo), child["end"] - child["start"] + 1,
                               yhi - ylo, fill=False, edgecolor=HL, lw=2.4, zorder=6))
        ax.annotate("zoom ↓", ((child["start"] + child["end"]) / 2, yhi), color=HL,
                    fontsize=9, ha="center", va="bottom", weight="bold", zorder=7)
    ax.set_title(f"{title}   ->   grade: {g.state}", fontsize=10, loc="left")
    ax.set_xlim(-pw - 3, len(win) + 2)
    ax.tick_params(labelsize=7)
    return g


def main():
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp("2024-09-01", tz="UTC")]

    spans = session_anchors(d5)
    sel = spans[-6:-1]                                    # ~5 sessions
    A = d5.iloc[sel[0]["start"]:sel[-1]["end"] + 1]
    cA = biggest_impulse(A)
    B = d1.loc[A.index[cA["start"]]:A.index[cA["end"]]]  # that impulse, on 1m
    cB = biggest_impulse(B)
    C = d1.loc[B.index[cB["start"]]:B.index[cB["end"]]] if cB else B

    fig, axes = plt.subplots(3, 1, figsize=(15, 13))
    panel(axes[0], A, f"(1) WIDEST  -  {len(sel)} sessions on 5m", child=cA)
    panel(axes[1], B, "(2) ZOOM into the box above  -  1m", child=cB)
    panel(axes[2], C, "(3) ZOOM into the box above  -  1m")
    fig.suptitle("Engine cascade - price within price within price: the SAME grade() at every zoom", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    out = os.path.join(HERE, "out", "cascade.png")
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == "__main__":
    main()
