"""experiments/engine/research/backtest_costs.py — net-of-costs equity (from cache).

Takes the cached 530-trade set and subtracts realistic trading costs, per trade, in R.
NQ (E-mini Nasdaq-100): $20 / point, tick = 0.25 pt = $5 / tick / contract.

Cost model (round turn):
  commission_rt  ($, default 4.00)              -> commission_rt / 20  points
  slip_ticks     (ticks PER SIDE, default 1)    -> slip_ticks * 2 * 0.25 points  (entry + exit)
Total cost is a FIXED number of points; expressed as R it is cost_points / (this trade's risk in
points), so tight-VA trades pay more R than wide-VA trades. Net R = gross R - cost R.

Compares the current 1.0R stop and the winning 0.8R stop, gross vs net, as equity curves.
Read-only; from cache (instant).

  python experiments/engine/research/backtest_costs.py --commission_rt 4 --slip_ticks 1
"""
import argparse
import glob
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from backtest_manage import sim_stop  # noqa: E402  (same rule)

POINT_VALUE = 20.0   # NQ E-mini: $ per index point
TICK = 0.25          # index points per tick


def load_cache(tag):
    path = os.path.join(ENGINE, "out", f"trades_cache_{tag}.pkl")
    if not os.path.exists(path):
        hits = sorted(glob.glob(os.path.join(ENGINE, "out", "trades_cache_*.pkl")))
        if not hits:
            sys.exit("no cached trades - run backtest_excursion.py first")
        path = hits[0]
    import pickle
    with open(path, "rb") as f:
        return pickle.load(f), os.path.basename(path)


def stats(rs):
    eq = np.cumsum(rs); peak = np.maximum.accumulate(eq)
    mdd = float((eq - peak).min()) if len(eq) else 0.0
    return dict(n=len(rs), win=float((np.array(rs) > 0).mean()),
                exp=float(np.mean(rs)), total=float(np.sum(rs)), mdd=mdd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="2020-01-01_0_0.3")
    ap.add_argument("--commission_rt", type=float, default=4.0, help="$ commission, round turn/contract")
    ap.add_argument("--slip_ticks", type=float, default=1.0, help="ticks of slippage PER SIDE")
    args = ap.parse_args()
    trades, name = load_cache(args.tag)
    dates = [t["date"] for t in trades]

    comm_pts = args.commission_rt / POINT_VALUE
    slip_pts = args.slip_ticks * 2 * TICK          # entry + exit
    cost_pts = comm_pts + slip_pts
    va = np.array([abs(t["entry"] - t["stop"]) for t in trades])   # 1.0R risk in points
    print(f"loaded {len(trades)} trades from {name}")
    print(f"cost/round-turn: ${args.commission_rt:.2f} comm + {args.slip_ticks:.0f} tick/side slip"
          f" = {cost_pts:.2f} pts (= ${cost_pts*POINT_VALUE:.0f})")
    print(f"VA width (1.0R risk): mean {va.mean():.1f} pts  median {np.median(va):.1f} pts  "
          f"min {va.min():.1f}  max {va.max():.1f}")

    fig, ax = plt.subplots(figsize=(13, 7))
    print(f"\n  {'variant':<26} {'n':>5} {'win%':>6} {'exp/R':>7} {'total':>8} {'maxDD':>7}")
    styles = [(1.0, "#4575b4"), (0.8, "#1a9850")]
    for f, col in styles:
        gross = np.array([sim_stop(t, f) for t in trades])
        risk_pts = f * va                          # actual $ risk per trade at this stop
        cost_R = cost_pts / risk_pts               # cost as a fraction of risk = R
        net = gross - cost_R
        sg = stats(gross); sn = stats(net)
        print(f"  {f:.1f}R stop  GROSS         {sg['n']:>5} {sg['win']*100:>5.0f}% {sg['exp']:>+7.2f} {sg['total']:>+8.1f} {sg['mdd']:>+7.1f}")
        print(f"  {f:.1f}R stop  NET (cost {cost_R.mean():.2f}R) {sn['n']:>5} {sn['win']*100:>5.0f}% {sn['exp']:>+7.2f} {sn['total']:>+8.1f} {sn['mdd']:>+7.1f}")
        ax.plot(dates, np.cumsum(gross), color=col, lw=1.3, ls=":", alpha=0.6,
                label=f"{f:.1f}R stop GROSS   ({sg['total']:+.0f}R, exp {sg['exp']:+.2f})")
        ax.plot(dates, np.cumsum(net), color=col, lw=2.1,
                label=f"{f:.1f}R stop NET     ({sn['total']:+.0f}R, exp {sn['exp']:+.2f}, DD {sn['mdd']:.0f})")

    ax.axhline(0, color="#999", lw=0.8); ax.grid(alpha=0.2)
    ax.set_title(f"Net-of-costs equity - NQ, {len(trades)} trades  "
                 f"(${args.commission_rt:.0f} comm + {args.slip_ticks:.0f} tick/side = {cost_pts:.2f} pt/RT)", fontsize=12)
    ax.set_ylabel("cumulative R"); ax.set_xlabel("date")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    out = os.path.join(ENGINE, "out", "backtest_costs.png")
    fig.savefig(out, dpi=120)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
