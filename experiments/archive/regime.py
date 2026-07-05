"""experiments/regime.py — TEMP throwaway. Multi-scale regime from session structure.

Two lenses per session:
  IMMEDIATE  — this session's break vs the PRIOR session's range (bull/bear/inside).
  STRUCTURAL — the current directional LEG (swing origin -> extreme) and how far price
               has RETRACED it. The leg only flips when the retrace gets deep.

Retracement zones (tunable):
  < pullback (0.50)      -> PULLBACK / re-accumulation, trend intact
  pullback..reversal     -> FUZZY (direction unclear)
  >= reversal (0.70)     -> REVERSAL (leg flips to the other side)

CONSOLIDATION override: if the last `window` sessions are boxed in a tight range
(combined range < `consol` x their average session range), price is going nowhere.

So a shallow counter-break reads as "immediate bear, structurally still bull, 30%
retraced" — a re-accumulation — while a deep one flips the structural trend.

Uses the same session grouping as the chart. Read-only. Delete when done.

Run (defaults NQ 5m, whole history):
  python experiments/regime.py
  python experiments/regime.py --start 2024-11-27 --recent 40
  python experiments/regime.py --pullback 0.5 --reversal 0.7 --consol 1.5 --window 4
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, deque

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from src.indicators.sessions import session_instances  # noqa: E402


def analyze(df, start, pullback, reversal, consol, window):
    df = df.loc[df.index >= pd.Timestamp(start, tz="UTC")]
    insts = session_instances(df, max_sessions=1_000_000)
    closes = df["close"].to_numpy()
    times = df.index

    rows = []
    # structural leg state
    d = None                 # 'bull' | 'bear'
    origin = extreme = pb = None
    pulling_back = False     # are we in a dip since the last new extreme?
    prev_hi = prev_lo = None
    recent = deque(maxlen=window)  # (hi, lo) for consolidation test

    for s in insts:
        hi, lo = float(s["hi_price"]), float(s["lo_price"])

        # --- immediate break vs prior session range (close-based) ---
        imm = "inside"
        if prev_hi is not None:
            for p in s["positions"]:
                c = float(closes[p])
                if c > prev_hi:
                    imm = "bull"; break
                if c < prev_lo:
                    imm = "bear"; break

        # --- structural leg + retracement ---
        if d is None:
            d, origin, extreme, pb = "bull", lo, hi, lo
            state, retr = "up", 0.0
        elif d == "bull":
            if hi >= extreme:                      # new high extends the leg
                if pulling_back:                   # a dip preceded it -> confirmed higher-low
                    origin = pb
                    pulling_back = False
                extreme = hi
                state, retr = "up", 0.0
            else:                                  # not a new high -> in a pullback
                if not pulling_back:
                    pulling_back, pb = True, lo
                else:
                    pb = min(pb, lo)
                span = extreme - origin
                retr = (extreme - pb) / span if span > 0 else 0.0
                if retr >= reversal:               # deep -> structural flip
                    d, origin, extreme = "bear", extreme, pb
                    pulling_back = False
                    state, retr = "rev_down", 0.0
                else:
                    state = "fuzzy" if retr >= pullback else "pullback"
        else:  # bear
            if lo <= extreme:
                if pulling_back:
                    origin = pb
                    pulling_back = False
                extreme = lo
                state, retr = "down", 0.0
            else:
                if not pulling_back:
                    pulling_back, pb = True, hi
                else:
                    pb = max(pb, hi)
                span = origin - extreme
                retr = (pb - extreme) / span if span > 0 else 0.0
                if retr >= reversal:
                    d, origin, extreme = "bull", extreme, pb
                    pulling_back = False
                    state, retr = "rev_up", 0.0
                else:
                    state = "fuzzy" if retr >= pullback else "pullback"

        # --- consolidation override (boxed range) ---
        recent.append((hi, lo))
        consolidating = False
        if len(recent) == window:
            net = max(h for h, _ in recent) - min(l for _, l in recent)
            avg = sum(h - l for h, l in recent) / window
            if avg > 0 and net < consol * avg:
                consolidating = True

        # --- regime label ---
        if consolidating:
            regime = "CONSOLIDATION"
        elif state == "up":
            regime = "TREND UP"
        elif state == "down":
            regime = "TREND DOWN"
        elif state in ("rev_up", "rev_down"):
            regime = "REVERSAL " + ("UP" if state == "rev_up" else "DOWN")
        elif state == "fuzzy":
            regime = "FUZZY"
        else:  # pullback
            regime = ("BULL" if d == "bull" else "BEAR") + " PULLBACK"

        rows.append({
            "time": times[s["start_pos"]], "sess": s["session"],
            "imm": imm, "trend": d, "retr": retr, "regime": regime,
        })
        prev_hi, prev_lo = hi, lo

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--start", default="2005-01-11")
    ap.add_argument("--pullback", type=float, default=0.50)
    ap.add_argument("--reversal", type=float, default=0.70)
    ap.add_argument("--consol", type=float, default=1.5)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--recent", type=int, default=30, help="how many recent sessions to list")
    args = ap.parse_args()

    path = os.path.join(REPO, "data", args.symbol, f"{args.symbol}_{args.tf}.parquet")
    df = pd.read_parquet(path)
    rows = analyze(df, args.start, args.pullback, args.reversal, args.consol, args.window)
    n = len(rows)

    line = "=" * 68
    print(line)
    print(f"  REGIME MAP - {args.symbol} {args.tf}  since {args.start}   ({n} sessions)")
    print(f"  rules: pullback<{args.pullback:.0%}  fuzzy {args.pullback:.0%}-{args.reversal:.0%}  "
          f"reversal>={args.reversal:.0%}  consol range<{args.consol}x")
    print(line)

    # how much time in each regime (group reversals under their trend for the tally)
    def bucket(r):
        if r.startswith("REVERSAL"):
            return "TREND UP" if r.endswith("UP") else "TREND DOWN"
        return r
    tally = Counter(bucket(r["regime"]) for r in rows)
    print("\n  TIME SPENT IN EACH REGIME:")
    for name in ["TREND UP", "TREND DOWN", "BULL PULLBACK", "BEAR PULLBACK", "FUZZY", "CONSOLIDATION"]:
        c = tally.get(name, 0)
        bar = "#" * round(c / n * 40)
        print(f"    {name:<14} {c/n:>5.0%}  {bar}")

    revs = sum(1 for r in rows if r["regime"].startswith("REVERSAL"))
    print(f"\n  structural reversals: {revs}   (~1 every {n/revs:.0f} sessions)" if revs else "")

    # recent timeline
    print(f"\n  LAST {args.recent} SESSIONS  (^ bull break, v bear, . inside):")
    print(f"    {'date':<11} {'sess':<7} {'break':<6} {'trend':<6} {'retrace':>7}  regime")
    sym = {"bull": "^", "bear": "v", "inside": "."}
    for r in rows[-args.recent:]:
        print(f"    {str(r['time'].date()):<11} {r['sess']:<7} {sym[r['imm']]:<6} "
              f"{r['trend']:<6} {r['retr']:>6.0%}  {r['regime']}")


if __name__ == "__main__":
    main()
