"""experiments/engine/validate_layers.py — show the recursion working.

DESCEND: chop #2 on 1-min -> tree (session -> impulses -> sub-impulses), same grade()
at every node. ASCEND: the last N sessions on 5m -> collapse to meta-candles -> one
multi-session grade.

  python experiments/engine/validate_layers.py
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from layers import descend, ascend, flatten  # noqa: E402
from anchors import session_anchors  # noqa: E402
from examples import pick_sessions  # noqa: E402


def main():
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    d1 = d1.loc[d1.index >= pd.Timestamp("2024-09-01", tz="UTC")]

    # --- DESCEND: chop #2 on 1m ---
    picks = pick_sessions(d5)
    (_, t0, t1), label = picks[3]
    win = d1.loc[(d1.index >= t0) & (d1.index <= t1 + pd.Timedelta("5min"))].reset_index(drop=True)
    tree = descend(win, max_depth=2)
    print(f"DESCEND - {label}  NY {t0.date()}  (session on 1-min, same grade() at every node)")
    print(f"  {'':<20}{'state':<14}{'net':>7} {'eff':>5} {'acc':>5} {'bars':>6}")
    names = {0: "SESSION", 1: "  impulse", 2: "    sub-impulse"}
    for depth, g, n in flatten(tree):
        print(f"  {names[depth]:<20}{g.state:<14}{g.net:>+7.0f} {g.efficiency:>5.2f} {g.acceptance:>5.2f} {n:>6}")

    # --- ASCEND: last 12 sessions on 5m ---
    spans = session_anchors(d5)[-12:]
    units = [d5.iloc[s["start"]:s["end"] + 1] for s in spans]
    top, unit_grades = ascend(units)
    print(f"\nASCEND - last {len(units)} sessions collapsed to meta-candles, then graded:")
    print(f"  per-session states: {[g.state.split()[0][:4] for g in unit_grades]}")
    print(f"  -> MULTI-SESSION grade: {top.state}  net {top.net:+.0f}  eff {top.efficiency:.2f}  "
          f"acc {top.acceptance:.2f}  strength {top.strength:+.0%}")


if __name__ == "__main__":
    main()
