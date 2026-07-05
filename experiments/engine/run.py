"""experiments/engine/run.py — render the engine's two views.

  drilldown.png  — per session: candles + impulse boxes + volume profile + the FULL
                   grade numbers, all in one panel (anatomy + states + profile unified).
  multiscale.png — one price chart with stacked regime ribbons (L3 span / L1 session /
                   L2 impulse), so every scale is visible at once and you see the nesting.

  python experiments/engine/run.py
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "experiments", "layer2"))
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import session_anchors, impulse_anchors, rolling_states  # noqa: E402
from session_legs import pick_sessions  # noqa: E402
import viz  # noqa: E402


def drilldown(d1, picks, out):
    fig, axes = plt.subplots(2, 1, figsize=(15, 11))
    for ((netp, t0, t1), label), ax in zip([picks[3], picks[0]], axes):
        win = d1.loc[(d1.index >= t0) & (d1.index <= t1 + pd.Timedelta("5min"))].reset_index(drop=True)
        g = grade(win)
        anchors = impulse_anchors(win)
        ylo, yhi = float(win["low"].min()), float(win["high"].max())
        pw = len(win) * 0.14
        viz.impulse_boxes(ax, anchors, ylo, yhi)
        viz.volume_profile(ax, win, g, pw)
        viz.candles(ax, win)
        viz.grade_textbox(ax, g)
        ax.set_title(f"{label}   NY {t0.date()}   ->   session grade: {g.state}", fontsize=10, loc="left")
        ax.set_xlim(-pw - 3, len(win) + 2)
        ax.tick_params(labelsize=7)
    fig.suptitle("Engine drill-down — impulse boxes + volume profile + the full grade, unified", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=110); print("wrote", out)


def segments_from(states):
    segs, i, n = [], 0, len(states)
    while i < n:
        if states[i] is None:
            i += 1; continue
        j = i
        while j < n and states[j] == states[i]:
            j += 1
        segs.append((i, j - 1, states[i])); i = j
    return segs


def multiscale(d5, out, n_sessions=8):
    spans = session_anchors(d5)[-n_sessions:]
    s0, s1 = spans[0]["start"], spans[-1]["end"]
    span = d5.iloc[s0:s1 + 1].reset_index(drop=True)
    n = len(span)

    l1 = [(sp["start"] - s0, sp["end"] - s0, grade(span.iloc[sp["start"] - s0:sp["end"] - s0 + 1]).state)
          for sp in spans]
    l2 = segments_from(rolling_states(span, 25))
    l3 = [(0, n - 1, grade(span).state)]

    fig = plt.figure(figsize=(16, 9))
    gs = fig.add_gridspec(4, 1, height_ratios=[0.5, 0.5, 0.5, 6], hspace=0.12)
    axL3, axL1, axL2, axP = (fig.add_subplot(gs[i]) for i in range(4))
    for ax, segs, lab in ((axL3, l3, "L3 span"), (axL1, l1, "L1 session"), (axL2, l2, "L2 impulse")):
        viz.ribbon(ax, segs, lab); ax.set_xlim(-0.5, n - 0.5)
    viz.candles(axP, span); axP.set_xlim(-2, n + 2); axP.tick_params(labelsize=7)
    handles = [Patch(color=c, label=s) for s, c in viz.STATE_COLOR.items()]
    axL3.legend(handles=handles, ncol=7, fontsize=7.5, loc="lower center",
                bbox_to_anchor=(0.5, 1.35), frameon=False)
    fig.suptitle(f"Engine multi-scale — {n_sessions} sessions (5m): same grade() at 3 scales at once", fontsize=12, y=0.97)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out, dpi=110); print("wrote", out)


def main():
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    picks = pick_sessions(d5)
    drilldown(d1, picks, os.path.join(HERE, "drilldown.png"))
    multiscale(d5, os.path.join(HERE, "multiscale.png"))


if __name__ == "__main__":
    main()
