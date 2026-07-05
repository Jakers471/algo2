"""experiments/engine/validate_grade.py — prove grade() == Layer-1 anatomy (no drift).

Grades the same 4 NY sessions the anatomy PNG uses, on the same 5m bars, and checks
every shared field against session_anatomy's own computation. The un-redefined metrics
must match EXACTLY. Two fields are intentionally redefined by GRADE_SPEC and are
reported separately, not as failures:
  - efficiency  : spec = |net|/travel  (anatomy showed range/travel "path_eff")
  - POC         : spec = fixed 24 rows  (anatomy used a 5.0 absolute row grid)

  python experiments/engine/validate_grade.py
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "experiments", "layer1"))
sys.path.insert(0, os.path.join(REPO, "experiments", "layer2"))
sys.path.insert(0, REPO)
from grade import grade                                   # noqa: E402
from session_anatomy import dims as adims, profile as aprofile  # noqa: E402
from session_legs import pick_sessions                    # noqa: E402

# grade attr -> anatomy dims key (shared, must match exactly)
SHARED = [("net", "net"), ("range", "rng"), ("strength", "net_pct"),
          ("body_pct", "body_pct"), ("close_pos", "close_pos"),
          ("up_wick", "up_wick"), ("low_wick", "low_wick"),
          ("travel", "travel"), ("swings", "swings"),
          ("t_high", "t_high"), ("t_low", "t_low"), ("vol", "vol"), ("delta", "delta")]


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp("2024-09-01", tz="UTC")]
    picks = pick_sessions(d5)

    all_ok = True
    for (netp, t0, t1), label in picks:
        win = d5.loc[(d5.index >= t0) & (d5.index <= t1)]
        g = grade(win)
        a = adims(win)
        print(f"\n=== {label}  NY {t0.date()}   (state: {g.state}) ===")
        for gattr, akey in SHARED:
            gv, av = getattr(g, gattr), a[akey]
            ok = close(float(gv), float(av))
            all_ok = all_ok and ok
            print(f"  {gattr:<10} grade={gv:>12.4f}   anatomy={av:>12.4f}   {'OK' if ok else 'DIFF <<'}")
        # intentional redefinitions — report, don't fail
        _, _, _, _, apoc = aprofile(win)
        print(f"  {'efficiency':<10} grade={g.efficiency:>12.4f}   (anatomy path_eff={a['path_eff']:.4f})  [redefined: |net|/travel]")
        print(f"  {'poc':<10} grade={g.poc:>12.1f}   (anatomy poc={apoc:.1f})  [redefined: 24 rows vs 5.0 grid]")

    print("\n" + ("ALL SHARED FIELDS MATCH - no accidental drift." if all_ok
                  else "!!! SOME SHARED FIELDS DIFFER - investigate."))


if __name__ == "__main__":
    main()
