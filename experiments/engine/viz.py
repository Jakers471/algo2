"""experiments/engine/viz.py — shared drawing for the engine.

One place for candles, impulse boxes, the volume profile, the grade text box, and
regime ribbons — so every view renders the SAME grade() output consistently.
"""
from __future__ import annotations

import os
import sys

from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
from src.indicators.volume_profile import _profile_for  # noqa: E402

STATE_COLOR = {
    "IMPULSE UP": "#1a9850", "IMPULSE DN": "#d73027",
    "GRIND UP": "#a7d8a0", "GRIND DN": "#f0a9a0",
    "CONSOLIDATION": "#5a8fd0", "WHIPSAW": "#b3b3b3", "UNCLEAR": "#e0e0e0",
}


def state_color(state):
    return STATE_COLOR.get(state, "#e0e0e0")


def candles(ax, win, zorder=2):
    o, h, l, c = (win[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    for i in range(len(c)):
        col = "#222" if c[i] >= o[i] else "#777"
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.4, zorder=zorder)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or 0.01,
                               color=col, lw=0, zorder=zorder))


def impulse_boxes(ax, anchors, ylo, yhi):
    for a in anchors:
        up = a["state"].endswith("UP")
        ax.add_patch(Rectangle((a["start"] - 0.5, ylo), a["end"] - a["start"] + 1, yhi - ylo,
                               color="#1a9850" if up else "#d73027", alpha=0.16, lw=0, zorder=1))


def volume_profile(ax, win, g, pw, n_rows=24):
    h = win["high"].to_numpy(float); l = win["low"].to_numpy(float); v = win["volume"].to_numpy(float)
    lo, hi = float(l.min()), float(h.max())
    rs = (hi - lo) / n_rows or 1e-9
    binvol = _profile_for(h, l, v, range(len(win)), lo, rs, n_rows)
    mx = float(binvol.max()) or 1.0
    poc_i = int(binvol.argmax())
    for r in range(n_rows):
        w = binvol[r] / mx * pw
        ax.add_patch(Rectangle((-pw - 1, lo + r * rs), w, rs,
                               color="#e08a1e" if r == poc_i else "#9aa6b0",
                               alpha=0.6 if r == poc_i else 0.3, lw=0, zorder=1))
    ax.axhline(g.poc, color="#e08a1e", lw=1.0, ls="--", zorder=3)
    ax.axhline(g.vah, color="#888", lw=0.6, ls=":", zorder=3)
    ax.axhline(g.val, color="#888", lw=0.6, ls=":", zorder=3)


def grade_textbox(ax, g):
    txt = (f"state: {g.state}\n"
           f"dir {g.direction}   strength {g.strength:+.0%}\n"
           f"efficiency {g.efficiency:.2f}   acceptance {g.acceptance:.2f}\n"
           f"range {g.range:.0f}   swings {g.swings}\n"
           f"close@{g.close_pos:.0%}   wick up {g.up_wick:.0%} / dn {g.low_wick:.0%}\n"
           f"POC {g.poc:.0f} @{g.poc_loc:.0%}   VAH {g.vah:.0f}  VAL {g.val:.0f}\n"
           f"vol {g.vol/1e3:.0f}k   delta {g.delta/1e3:+.0f}k")
    ax.text(0.015, 0.985, txt, transform=ax.transAxes, va="top", ha="left", fontsize=7.5,
            family="monospace", bbox=dict(boxstyle="round", fc="white", ec="#bbb", alpha=0.92))


def ribbon(ax, segments, label):
    """segments: [(start, end, state)]. Draws a full-height colored strip."""
    for start, end, state in segments:
        ax.add_patch(Rectangle((start, 0), end - start + 1, 1, color=state_color(state), lw=0))
    ax.set_ylim(0, 1)
    ax.set_yticks([]); ax.set_xticks([])
    ax.text(-0.006, 0.5, label, transform=ax.transAxes, ha="right", va="center",
            fontsize=8, family="monospace")
