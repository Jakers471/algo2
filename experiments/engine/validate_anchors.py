"""experiments/engine/validate_anchors.py — do impulse_anchors match leg_states?

Detects structure impulses on chop #2 + strongest bull (1-min) and shades them, so we
can eyeball against experiments/archive/layer2/leg_states.png (should be the same green/red
regions). Also prints each impulse anchor's span + price move.

  python experiments/engine/validate_anchors.py
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
from anchors import impulse_anchors  # noqa: E402
from examples import pick_sessions  # noqa: E402


def plot(ax, win, title):
    o, h, l, c = (win[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    anchors = impulse_anchors(win)   # window=25, gap=12, min_len=8
    for a in anchors:
        up = a["state"].endswith("UP")
        ax.add_patch(Rectangle((a["start"] - 0.5, l.min()), a["end"] - a["start"] + 1, h.max() - l.min(),
                               color="#1a9850" if up else "#d73027", alpha=0.18, lw=0, zorder=1))
    for i in range(n):
        cc = "#111" if c[i] >= o[i] else "#555"
        ax.plot([i, i], [l[i], h[i]], color=cc, lw=0.4, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or 0.01, color=cc, lw=0, zorder=2))
    ax.set_title(f"{title}   ({len(anchors)} impulse anchors)", fontsize=10, loc="left")
    ax.set_xlim(-2, n + 2)
    ax.tick_params(labelsize=7)
    return anchors, c


def main():
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    picks = pick_sessions(d5)
    chosen = [picks[3], picks[0]]     # chop #2, strongest bull

    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    for ((netp, t0, t1), label), ax in zip(chosen, axes):
        win = d1.loc[(d1.index >= t0) & (d1.index <= t1 + pd.Timedelta("5min"))].reset_index(drop=True)
        anchors, c = plot(ax, win, f"{label}  NY {t0.date()}")
        print(f"\n{label}  NY {t0.date()}  -> {len(anchors)} impulse anchors:")
        for a in anchors:
            move = c[a["end"]] - c[a["start"]]
            print(f"   bars {a['start']:>3}-{a['end']:<3}  {a['state']:<11} move {move:+.0f} pts")
    fig.suptitle("Engine step 2 — structure-detected IMPULSE anchors (compare to leg_states.png)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(HERE, "out", "anchors_check.png")
    fig.savefig(out, dpi=110)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
