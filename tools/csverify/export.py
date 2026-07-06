"""Step 1 of the C#<->Python equivalence check: export test windows + Python-SOURCE
expected values (from the frozen grade.py / consolidation.py) to input.json.

Run from anywhere:  python lean/vabreakout_cs/verify/export.py
"""
import os
import sys
import json

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))                    # csverify -> tools -> repo
sys.path.insert(0, os.path.join(REPO, "experiments", "engine"))
sys.path.insert(0, os.path.join(REPO, "src", "strategy", "readings"))
from grade import grade as gsrc                     # the frozen source of truth  # noqa: E402
import consolidation as cons_src                     # noqa: E402

d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
d1 = d1.loc[d1.index >= pd.Timestamp("2024-01-01", tz="UTC")]
cases = []
for pos in range(300, len(d1), 7000):                # ~50 windows spread across 2024
    w = d1.iloc[pos - 300:pos]
    o, h, l, c, v = (w[k].to_numpy(float).tolist() for k in ["open", "high", "low", "close", "volume"])
    pc = cons_src.read_consolidation(w)              # source consolidation (last-120 detection)
    g60 = gsrc(w.tail(60))                            # source grade on the last 60 bars
    cases.append({
        "o": o, "h": h, "l": l, "c": c, "v": v,
        "py_cons": pc,
        "py_g60": {"state": g60.state, "strength": g60.strength, "vah": g60.vah,
                   "val": g60.val, "acc": g60.acceptance, "poc": g60.poc},
    })
json.dump(cases, open(os.path.join(HERE, "input.json"), "w"))
print(f"exported {len(cases)} cases -> input.json")
