"""experiments/engine/research/backtest_manage.py — stop sweep + trailing runner (from cache).

Loads the cached trade set (out/trades_cache_*.pkl, built by backtest_excursion.py) and runs
two management experiments off it, so both are INSTANT (no 1m re-grading):

  1. STOP SWEEP - keep the 2R profit target (2x VA width) at a fixed price, but move the stop
     closer: 0.7 / 0.8 / 0.9 / 1.0 x VA. Risk-normalized (constant risk per trade): a stop-out
     is always -1R; because a tighter stop = bigger size for the same risk, a win that reaches
     the same target price is worth 2/f R. So tighter stop -> bigger wins but more stop-outs.

  2. TRAILING RUNNER - baseline 1R stop; scale HALF off at +2R (locks +1.0R), then trail the
     other half by 1R (1x VA) behind the peak, exiting on the retrace or at session close.
     Compared head-to-head with the current fixed-2R exit.

Both drawn as equity curves (cumulative R). Read-only; optimistic fills.

  python experiments/engine/research/backtest_manage.py
"""
import argparse
import glob
import os
import pickle
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)


def load_cache(tag):
    path = os.path.join(ENGINE, "out", f"trades_cache_{tag}.pkl") if tag else None
    if not path or not os.path.exists(path):
        hits = sorted(glob.glob(os.path.join(ENGINE, "out", "trades_cache_*.pkl")))
        if not hits:
            sys.exit("no cached trades - run backtest_excursion.py first")
        path = hits[0]
    with open(path, "rb") as f:
        trades = pickle.load(f)
    print(f"loaded {len(trades)} trades from {os.path.basename(path)}")
    return trades


def sim_stop(t, f, tmult=2.0):
    """Fixed target price (tmult x VA), stop at f x VA. Risk-normalized: loss -1R, win tmult/f R."""
    e = t["entry"]; va = abs(e - t["stop"]); side = t["side"]
    h, l, c = t["h"], t["l"], t["c"]
    if side == "long":
        stop_px = e - f * va; target_px = e + tmult * va
        for k in range(len(c)):
            if l[k] <= stop_px:
                return -1.0
            if h[k] >= target_px:
                return tmult / f
        return (c[-1] - e) / (f * va)
    else:
        stop_px = e + f * va; target_px = e - tmult * va
        for k in range(len(c)):
            if h[k] >= stop_px:
                return -1.0
            if l[k] <= target_px:
                return tmult / f
        return (e - c[-1]) / (f * va)


def sim_runner(t, scale_R=2.0, trail_R=1.0):
    """1R stop; scale 50% at +scale_R (locks 0.5*scale_R); trail other 50% by trail_R behind peak."""
    e = t["entry"]; va = abs(e - t["stop"]); side = t["side"]
    h, l, c = t["h"], t["l"], t["c"]
    locked = 0.5 * scale_R
    if side == "long":
        stop_px = e - va; scale_px = e + scale_R * va
        scaled = False; peak = e
        for k in range(len(c)):
            if not scaled:
                if l[k] <= stop_px:
                    return -1.0
                if h[k] >= scale_px:
                    scaled = True; peak = max(peak, h[k])
                continue
            peak = max(peak, h[k])
            trail = max(e, peak - trail_R * va)
            if l[k] <= trail:
                return locked + 0.5 * (trail - e) / va
        return locked + 0.5 * (c[-1] - e) / va if scaled else (c[-1] - e) / va
    else:
        stop_px = e + va; scale_px = e - scale_R * va
        scaled = False; trough = e
        for k in range(len(c)):
            if not scaled:
                if h[k] >= stop_px:
                    return -1.0
                if l[k] <= scale_px:
                    scaled = True; trough = min(trough, l[k])
                continue
            trough = min(trough, l[k])
            trail = min(e, trough + trail_R * va)
            if h[k] >= trail:
                return locked + 0.5 * (e - trail) / va
        return locked + 0.5 * (e - c[-1]) / va if scaled else (e - c[-1]) / va


def stats(rs):
    eq = np.cumsum(rs); peak = np.maximum.accumulate(eq)
    mdd = float((eq - peak).min()) if len(eq) else 0.0
    return dict(n=len(rs), win=float((np.array(rs) > 0).mean()),
                exp=float(np.mean(rs)), total=float(np.sum(rs)), mdd=mdd)


def line(label, rs):
    s = stats(rs)
    print(f"  {label:<22} {s['n']:>5} {s['win']*100:>5.0f}% {s['exp']:>+7.2f} {s['total']:>+8.1f} {s['mdd']:>+7.1f}")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="2020-01-01_0_0.3")
    args = ap.parse_args()
    trades = load_cache(args.tag)
    dates = [t["date"] for t in trades]

    fig, ax = plt.subplots(1, 2, figsize=(16, 7))

    # ---- 1. stop sweep ----
    print("\n" + "=" * 62)
    print("  1. STOP SWEEP  (2R target fixed, stop moved closer; risk-normalized)")
    print("=" * 62)
    print(f"  {'variant':<22} {'n':>5} {'win%':>6} {'exp/R':>7} {'total':>8} {'maxDD':>7}")
    sweep = [(0.7, "#d73027"), (0.8, "#fc8d59"), (0.9, "#91bfdb"), (1.0, "#4575b4")]
    for f, col in sweep:
        rs = [sim_stop(t, f) for t in trades]
        s = line(f"stop {f:.1f}R  (win {2/f:.2f}R)", rs)
        ax[0].plot(dates, np.cumsum(rs), color=col, lw=1.8,
                   label=f"stop {f:.1f}R -> win {2/f:.2f}R   ({s['total']:+.0f}R, exp {s['exp']:+.2f}, DD {s['mdd']:.0f})")
    ax[0].axhline(0, color="#999", lw=0.8); ax[0].grid(alpha=0.2)
    ax[0].set_title("1. Stop sweep - 2R target fixed, stop tightened (risk-normalized)")
    ax[0].set_ylabel("cumulative R"); ax[0].legend(loc="upper left", fontsize=8.5)

    # ---- 2. trailing runner vs fixed 2R ----
    print("\n" + "=" * 62)
    print("  2. TRAILING RUNNER  vs  fixed 2R  (both 1R stop)")
    print("=" * 62)
    print(f"  {'variant':<22} {'n':>5} {'win%':>6} {'exp/R':>7} {'total':>8} {'maxDD':>7}")
    rs_fixed = [sim_stop(t, 1.0) for t in trades]
    rs_run = [sim_runner(t) for t in trades]
    sf = line("fixed 2R", rs_fixed)
    sr = line("half@2R + trail 1R", rs_run)
    ax[1].plot(dates, np.cumsum(rs_fixed), color="#4575b4", lw=1.9,
               label=f"fixed 2R   ({sf['total']:+.0f}R, exp {sf['exp']:+.2f}, DD {sf['mdd']:.0f})")
    ax[1].plot(dates, np.cumsum(rs_run), color="#1a9850", lw=1.9,
               label=f"half@2R + trail 1R   ({sr['total']:+.0f}R, exp {sr['exp']:+.2f}, DD {sr['mdd']:.0f})")
    ax[1].axhline(0, color="#999", lw=0.8); ax[1].grid(alpha=0.2)
    ax[1].set_title("2. Trailing runner vs fixed 2R (both 1R stop)")
    ax[1].set_ylabel("cumulative R"); ax[1].legend(loc="upper left", fontsize=9)

    fig.suptitle(f"Management experiments (from cache, {len(trades)} trades) - stop sweep + trailing runner", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(ENGINE, "out", "backtest_manage.png")
    fig.savefig(out, dpi=120)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
