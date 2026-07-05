"""experiments/engine/research/backtest_cont.py — test: value-area breakout in a directional session.

The rule (no lookahead):
  - At each 1m CONSOLIDATION inside a session, grade the session ONLY up to the setup
    (bars open..consolidation-start). If that is directional -> bias = its direction.
  - bull bias: go LONG on a close above the consolidation's VAH; stop = VAL.
  - bear bias: go SHORT on a close below VAL; stop = VAH.
  - risk R = VAH - VAL. Target = 2R. Exit on stop, target, or session close (intraday).

Reports win rate, expectancy (avg R), target/stop hit rates, MFE/MAE. Also runs a
NO-FILTER control (all consolidation breakouts) to show what the session-bias filter adds.
Optimistic fills (entry at the level). Read-only; frozen engine.

  python experiments/engine/research/backtest_cont.py --sessions 300
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ENGINE))
sys.path.insert(0, ENGINE)
sys.path.insert(0, REPO)
from grade import grade  # noqa: E402
from anchors import session_anchors, rolling_states  # noqa: E402

UP = ("IMPULSE UP", "GRIND UP")
DN = ("IMPULSE DN", "GRIND DN")


def cons_runs(states, min_len=15):
    out, i = [], 0
    while i < len(states):
        j = i
        while j < len(states) and states[j] == states[i]:
            j += 1
        if states[i] == "CONSOLIDATION" and j - i >= min_len:
            out.append((i, j - 1))
        i = j
    return out


def simulate(entry, stop, target, side, h, l, c):
    """Walk bars h/l/c forward; return (R_result, mfe_R, mae_R)."""
    risk = abs(entry - stop)
    mfe = mae = 0.0
    for k in range(len(c)):
        if side == "long":
            mfe = max(mfe, (h[k] - entry) / risk); mae = min(mae, (l[k] - entry) / risk)
            if l[k] <= stop:
                return -1.0, mfe, mae
            if h[k] >= target:
                return 2.0, mfe, mae
        else:
            mfe = max(mfe, (entry - l[k]) / risk); mae = min(mae, (entry - h[k]) / risk)
            if h[k] >= stop:
                return -1.0, mfe, mae
            if l[k] <= target:
                return 2.0, mfe, mae
    return (c[-1] - entry) / risk * (1 if side == "long" else -1), mfe, mae


def run(d5, d1, spans, use_filter, bias_str=0.3):
    trades = []
    for s in spans:
        win1 = d1.loc[d5.index[s["start"]]:d5.index[s["end"]] + pd.Timedelta("5min")]
        if len(win1) < 60:
            continue
        st = rolling_states(win1, 25)
        h = win1["high"].to_numpy(float); l = win1["low"].to_numpy(float); c = win1["close"].to_numpy(float)
        for a, b in cons_runs(st):
            if a < 20 or b + 2 >= len(win1):
                continue
            g = grade(win1.iloc[a:b + 1])
            vah, val = g.vah, g.val
            if vah <= val:
                continue
            # session-so-far bias (no lookahead) — directional = strength (net/range) beyond threshold
            gs = grade(win1.iloc[:a])
            if gs.strength >= bias_str:
                bias = "long"
            elif gs.strength <= -bias_str:
                bias = "short"
            else:
                bias = None
            if use_filter and bias is None:
                continue
            # if no filter, allow both-direction breakouts (take whichever triggers first)
            risk = vah - val
            fut_h, fut_l, fut_c = h[b + 1:], l[b + 1:], c[b + 1:]
            # find first break
            for k in range(len(fut_c)):
                up_break = fut_c[k] > vah
                dn_break = fut_c[k] < val
                if not (up_break or dn_break):
                    continue
                side = "long" if up_break else "short"
                if use_filter and ((bias == "long") != (side == "long")):
                    # only take breaks in the session-bias direction
                    if bias == "long" and not up_break:
                        break
                    if bias == "short" and not dn_break:
                        break
                entry = vah if side == "long" else val
                stop = val if side == "long" else vah
                target = entry + 2 * risk if side == "long" else entry - 2 * risk
                r, mfe, mae = simulate(entry, stop, target, side, fut_h[k:], fut_l[k:], fut_c[k:])
                trades.append((r, mfe, mae, side))
                break
    return trades


def summary(trades, label):
    if not trades:
        print(f"  {label}: no trades"); return
    rs = np.array([t[0] for t in trades])
    wins = (rs > 0).mean()
    print(f"  {label}: {len(trades)} trades | win {wins:.0%} | avg {rs.mean():+.2f}R | "
          f"hit +2R {np.mean(rs >= 2):.0%} | stopped {np.mean(rs <= -1):.0%} | "
          f"avg MFE {np.mean([t[1] for t in trades]):.1f}R / MAE {np.mean([t[2] for t in trades]):.1f}R")
    return rs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--sessions", type=int, default=300)
    ap.add_argument("--bias_str", type=float, default=0.3, help="|net/range| so far to call the session directional")
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)[-args.sessions:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[spans[0]["start"]]]

    print("=" * 66)
    print(f"  BACKTEST: value-area breakout continuation  (NQ, {len(spans)} sessions, 1m)")
    print(f"  entry = break of VAH/VAL, stop = opposite edge (risk=VA height), target 2R, exit at session close")
    print("=" * 66)
    filt = run(d5, d1, spans, use_filter=True, bias_str=args.bias_str)
    ctrl = run(d5, d1, spans, use_filter=False)
    rf = summary(filt, "WITH session-bias filter (the rule)")
    summary(ctrl, "control: ALL breakouts (no filter)")

    if rf is not None and len(rf):
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(np.clip(rf, -1.2, 2.2), bins=24, color="#4575b4", edgecolor="white")
        ax.axvline(0, color="#888", lw=1); ax.axvline(rf.mean(), color="#1a9850", lw=2, ls="--",
                                                       label=f"expectancy {rf.mean():+.2f}R")
        ax.set_title(f"Trade outcomes (R) - VA breakout in a directional session  (n={len(rf)})")
        ax.set_xlabel("R result per trade"); ax.legend()
        fig.tight_layout()
        out = os.path.join(ENGINE, "out", "backtest_cont.png")
        fig.savefig(out, dpi=110); print("\nwrote", out)


if __name__ == "__main__":
    main()
