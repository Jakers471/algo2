"""experiments/break_sequence.py — TEMP throwaway. Mine the bull/bear break sequence.

Each SESSION is a break: BULL if its first close beyond the PREVIOUS session's range
is above the prior high, BEAR if below the prior low (whichever comes first). Sessions
that never close beyond the prior range are INSIDE (excluded from the run stats by
default; reported separately).

Then it analyses the sequence of bull/bear breaks:
  - base rates + the bull/bear transition matrix,
  - run-length distributions,
  - CONTINUATION odds: given a bull run reached length k, how often it reaches k+1
    ("1 bull -> 2 -> 3 -> ..."), and the same for bear,
  - the longest runs.

Uses the SAME session grouping as the chart (src.indicators.sessions), so it matches
what you see. Pure read-only analysis. Delete when done.

Run (defaults to NQ 5m from 2024-11-27):
  python experiments/break_sequence.py
  python experiments/break_sequence.py --symbol NQ --tf 5m --start 2024-11-27
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from src.indicators.sessions import session_instances  # noqa: E402


def classify(df, start):
    """-> list of (session_name, day_ts, 'bull'|'bear'|'inside') in time order."""
    df = df.loc[df.index >= pd.Timestamp(start, tz="UTC")]
    insts = session_instances(df, max_sessions=1_000_000)  # ALL sessions in range
    closes = df["close"].to_numpy()
    times = df.index

    out = []
    ref_hi = ref_lo = None
    for s in insts:
        tag = "inside"
        if ref_hi is not None:
            for p in s["positions"]:
                c = float(closes[p])
                if c > ref_hi:
                    tag = "bull"; break
                if c < ref_lo:
                    tag = "bear"; break
        out.append((s["session"], times[s["start_pos"]], tag))
        ref_hi, ref_lo = float(s["hi_price"]), float(s["lo_price"])
    return out


def runs(seq):
    """Compress a list into (value, run_length) pairs."""
    r = []
    for v in seq:
        if r and r[-1][0] == v:
            r[-1] = (v, r[-1][1] + 1)
        else:
            r.append((v, 1))
    return r


def streak_story(lengths, word):
    """Plain-English continuation odds for one side's streaks."""
    if not lengths:
        print(f"  No {word} streaks in this range.")
        return
    total = len(lengths)
    longest = max(lengths)
    print(f"  There were {total} {word} streaks. The longest was {longest} in a row.")
    print()
    for k in range(1, longest + 1):
        reached = sum(1 for x in lengths if x >= k)     # streaks that got to k
        went_on = sum(1 for x in lengths if x >= k + 1)  # ...and kept going to k+1
        if reached == 0:
            break
        chance = went_on / reached
        if k == 1:
            line = f"  You just saw 1 {word} break  ->  {chance:.0%} chance the NEXT break is {word} too"
        else:
            line = f"  {word.capitalize()} has broken {k} times in a row  ->  {chance:.0%} chance of one more"
        note = f"   (happened {went_on} of the {reached} times)"
        if reached < 4:
            note += "  [only a few samples - take with a grain of salt]"
        print(line)
        print(note)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--start", default="2024-11-27")
    ap.add_argument("--show-seq", action="store_true", help="print the full B/E/- sequence")
    args = ap.parse_args()

    path = os.path.join(REPO, "data", args.symbol, f"{args.symbol}_{args.tf}.parquet")
    df = pd.read_parquet(path)
    tagged = classify(df, args.start)

    seq_all = [t for _, _, t in tagged]
    n = len(seq_all)
    nb = seq_all.count("bull")
    ne = seq_all.count("bear")
    ni = seq_all.count("inside")
    decisive = [t for t in seq_all if t != "inside"]  # bull/bear only

    def pct(x):
        return f"{x/len(decisive):.0%}" if decisive else "0%"

    line = "=" * 60
    print(line)
    print(f"  {args.symbol} {args.tf} sessions since {args.start}")
    print(f"  {tagged[0][1].date()} to {tagged[-1][1].date()}")
    print(line)
    print()
    print(f"  Out of {n} sessions:")
    print(f"    {nb} broke BULLISH (closed above the prior session's high)   {nb/n:.0%}")
    print(f"    {ne} broke BEARISH (closed below the prior session's low)     {ne/n:.0%}")
    print(f"    {ni} did nothing (stayed inside the prior range)              {ni/n:.0%}")
    print()

    # what usually comes next
    print("  WHAT COMES NEXT AFTER A BREAK")
    for a in ("bull", "bear"):
        pairs = [decisive[i + 1] for i in range(len(decisive) - 1) if decisive[i] == a]
        tot = len(pairs)
        same = sum(1 for y in pairs if y == a)
        other = "bear" if a == "bull" else "bull"
        print(f"  After a {a} break, the next break is "
              f"{a} {same/tot:.0%} of the time, {other} {(tot-same)/tot:.0%}.")
    print()

    rl = runs(decisive)
    bull_runs = [ln for v, ln in rl if v == "bull"]
    bear_runs = [ln for v, ln in rl if v == "bear"]

    print("  HOW LONG DO BULLISH STREAKS RUN?")
    print("  (a streak = bullish breaks back-to-back)")
    streak_story(bull_runs, "bull")
    print()
    print("  HOW LONG DO BEARISH STREAKS RUN?")
    streak_story(bear_runs, "bear")

    if args.show_seq:
        print()
        sym = {"bull": "^", "bear": "v", "inside": "."}
        print("  each session in order (^ bull, v bear, . inside):")
        print("  " + "".join(sym[t] for t in seq_all))


if __name__ == "__main__":
    main()
