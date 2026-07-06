"""experiments/engine/research/backtest_equity.py — multi-year equity curves.

Same setup as backtest_cont.py (VA breakout in a directional session, no lookahead), but
run over YEARS and drawn as an equity curve (cumulative R). Collects each trade once, then
simulates it under four management variants so the curves are directly comparable:

  - target 2R, hard stop            - target 3R, hard stop
  - target 2R, breakeven at +1R     - target 3R, breakeven at +1R

"Breakeven at +1R" = once price trades +1R in favor, the stop moves to entry (a scratch,
0R, instead of a full -1R loss). Optimistic fills (entry at the level, no slippage/commission).
Read-only; frozen engine.

  python experiments/engine/research/backtest_equity.py --start 2020-01-01
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


def sim(entry, stop, side, h, l, c, target_mult, breakeven):
    """One trade under a given management. Returns R.

    breakeven: once +1R is reached, the stop is moved to entry (scratch instead of -1R).
    Intrabar convention: check the stop before the target/arming (conservative)."""
    risk = abs(entry - stop)
    target = entry + target_mult * risk if side == "long" else entry - target_mult * risk
    cur_stop = stop
    armed = False
    for k in range(len(c)):
        if side == "long":
            if l[k] <= cur_stop:
                return (cur_stop - entry) / risk
            if h[k] >= target:
                return target_mult
            if breakeven and not armed and h[k] >= entry + risk:
                armed = True; cur_stop = entry
        else:
            if h[k] >= cur_stop:
                return (entry - cur_stop) / risk
            if l[k] <= target:
                return target_mult
            if breakeven and not armed and l[k] <= entry - risk:
                armed = True; cur_stop = entry
    return (c[-1] - entry) / risk * (1 if side == "long" else -1)


def collect(d5, d1, spans, bias_str=0.3):
    """Find every trade once: (date, side, entry, stop, future h/l/c). Management applied later."""
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
            g = grade(win1.iloc[a:b + 1]); vah, val = g.vah, g.val
            if vah <= val:
                continue
            gs = grade(win1.iloc[:a])
            bias = "long" if gs.strength >= bias_str else "short" if gs.strength <= -bias_str else None
            if bias is None:
                continue
            for k in range(b + 1, len(win1)):
                up_b, dn_b = c[k] > vah, c[k] < val
                if (bias == "long" and dn_b) or (bias == "short" and up_b):
                    break  # base broke the wrong way first -> abandon
                if (bias == "long" and up_b) or (bias == "short" and dn_b):
                    side = bias
                    entry = vah if side == "long" else val
                    stop = val if side == "long" else vah
                    trades.append(dict(date=win1.index[k], side=side, entry=entry, stop=stop,
                                       h=h[k:], l=l[k:], c=c[k:]))
                    break
    return trades


def curve(trades, target_mult, breakeven):
    rs = np.array([sim(t["entry"], t["stop"], t["side"], t["h"], t["l"], t["c"], target_mult, breakeven)
                   for t in trades])
    return rs


def stats(rs):
    eq = np.cumsum(rs)
    peak = np.maximum.accumulate(eq)
    mdd = float((eq - peak).min()) if len(eq) else 0.0
    return dict(n=len(rs), win=float((rs > 0).mean()), scratch=float(np.mean(np.abs(rs) < 1e-9)),
                exp=float(rs.mean()), total=float(rs.sum()), mdd=mdd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--sessions", type=int, default=0, help="0 = all sessions since --start")
    ap.add_argument("--bias_str", type=float, default=0.3)
    args = ap.parse_args()
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(args.start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)
    if args.sessions:
        spans = spans[-args.sessions:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[spans[0]["start"]]]

    trades = collect(d5, d1, spans, args.bias_str)
    dates = [t["date"] for t in trades]
    print("=" * 78)
    print(f"  EQUITY: VA breakout in a directional session  (NQ 1m)")
    print(f"  {len(spans)} sessions  {d5.index[spans[0]['start']].date()} -> {d5.index[spans[-1]['end']].date()}"
          f"   |   {len(trades)} trades")
    print("=" * 78)

    variants = [("2R hard stop", 2.0, False, "#4575b4", "-"),
                ("2R breakeven@1R", 2.0, True, "#91bfdb", "--"),
                ("3R hard stop", 3.0, False, "#d73027", "-"),
                ("3R breakeven@1R", 3.0, True, "#fc8d59", "--")]

    fig, ax = plt.subplots(figsize=(13, 7))
    print(f"  {'variant':<20} {'trades':>6} {'win%':>6} {'scr%':>6} {'exp/R':>7} {'total R':>8} {'maxDD':>7}")
    for label, tm, be, col, ls in variants:
        rs = curve(trades, tm, be)
        s = stats(rs)
        print(f"  {label:<20} {s['n']:>6} {s['win']*100:>5.0f}% {s['scratch']*100:>5.0f}% "
              f"{s['exp']:>+7.2f} {s['total']:>+8.1f} {s['mdd']:>+7.1f}")
        ax.plot(dates, np.cumsum(rs), color=col, ls=ls, lw=1.8,
                label=f"{label}   ({s['total']:+.0f}R, exp {s['exp']:+.2f}, DD {s['mdd']:.0f})")

    ax.axhline(0, color="#999", lw=0.8)
    ax.set_title(f"Equity curve (cumulative R) - VA breakout, {d5.index[spans[0]['start']].date()} to {d5.index[spans[-1]['end']].date()}", fontsize=12)
    ax.set_ylabel("cumulative R"); ax.set_xlabel("date")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    out = os.path.join(ENGINE, "out", "backtest_equity.png")
    fig.savefig(out, dpi=120)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
