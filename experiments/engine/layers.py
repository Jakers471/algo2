"""experiments/engine/layers.py — the recursion. One grade(), up and down scales.

GRADE_SPEC §4:
  - DESCEND (zoom in): grade an anchor, then recurse into its IMPULSE sub-anchors.
  - ASCEND  (zoom out): collapse a sequence of anchors to meta-candles, grade that.

Both call the same grade() — that's what makes the layers one design, not cousins.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import impulse_anchors, meta_frame  # noqa: E402

MIN_DESCEND = 30   # need enough bars under an anchor to scan for sub-impulses


def descend(bars, max_depth=2, depth=0):
    """Grade `bars` as one anchor, then recurse into its IMPULSE sub-anchors.
    -> nested {grade, n, depth, children}."""
    node = {"grade": grade(bars), "n": len(bars), "depth": depth, "children": []}
    if depth < max_depth and len(bars) >= MIN_DESCEND:
        for s in impulse_anchors(bars):
            sub = bars.iloc[s["start"]:s["end"] + 1]
            node["children"].append(descend(sub, max_depth, depth + 1))
    return node


def ascend(units):
    """units: OHLCV frames in time order (e.g. sessions). Grade each, collapse to
    meta-candles, grade the sequence. -> (top_grade, [unit_grades])."""
    grades = [grade(b) for b in units]
    return grade(meta_frame(grades)), grades


def flatten(node, out=None):
    """Depth-first list of (depth, grade, n) for printing."""
    out = [] if out is None else out
    out.append((node["depth"], node["grade"], node["n"]))
    for c in node["children"]:
        flatten(c, out)
    return out
