"""backtests/sim_curves.py — plot equity curves for many manage strategies on the local sim.

Reuses backtests/sim.py (base trades + bar-by-bar manage replay). Every curve is cumulative R
at CONSTANT $ risk per trade (each config's R = its own initial stop distance), so they're
directly comparable. One PNG, all curves, ranked legend.
"""
import os
import pickle
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

START, END = "2022-01-01", "2025-01-01"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_equity_curves.png")

CONFIGS = [
    ("baseline: VA stop, 2R",        dict(stop_mult=1.0, be_trigger=None, target_R=2.0, trail_R=None)),
    ("tighter stop 0.7, 2R",         dict(stop_mult=0.7, be_trigger=None, target_R=2.0, trail_R=None)),
    ("tighter stop 0.85, 2R",        dict(stop_mult=0.85, be_trigger=None, target_R=2.0, trail_R=None)),
    ("wider stop 1.3, 2R",           dict(stop_mult=1.3, be_trigger=None, target_R=2.0, trail_R=None)),
    ("wider stop 1.5, 2R",           dict(stop_mult=1.5, be_trigger=None, target_R=2.0, trail_R=None)),
    ("target 3R",                    dict(stop_mult=1.0, be_trigger=None, target_R=3.0, trail_R=None)),
    ("target 4R",                    dict(stop_mult=1.0, be_trigger=None, target_R=4.0, trail_R=None)),
    ("target 5R",                    dict(stop_mult=1.0, be_trigger=None, target_R=5.0, trail_R=None)),
    ("breakeven 0.5R, 2R",           dict(stop_mult=1.0, be_trigger=0.5, target_R=2.0, trail_R=None)),
    ("breakeven 1.0R, 2R",           dict(stop_mult=1.0, be_trigger=1.0, target_R=2.0, trail_R=None)),
    ("trail 1R (no target)",         dict(stop_mult=1.0, be_trigger=None, target_R=None, trail_R=1.0)),
    ("trail 1.5R (no target)",       dict(stop_mult=1.0, be_trigger=None, target_R=None, trail_R=1.5)),
    ("trail 2R (no target)",         dict(stop_mult=1.0, be_trigger=None, target_R=None, trail_R=2.0)),
    ("wider 1.5 + target 4R",        dict(stop_mult=1.5, be_trigger=None, target_R=4.0, trail_R=None)),
    ("wider 1.5 + trail 2R",         dict(stop_mult=1.5, be_trigger=None, target_R=None, trail_R=2.0)),
]


def curve(h, l, c, trades, cfg):
    Rs = [r[0] for tr in trades if (r := sim.simulate(h, l, c, tr, cfg)) is not None]
    return np.cumsum(Rs), float(np.mean(Rs)), float(np.mean(np.array(Rs) > 0) * 100)


def main():
    o, h, l, c, v, mod, epoch = sim.load(START, END)
    trades = pickle.load(open(os.path.join(sim.CACHE, f"trades_{START}_{END}.pkl"), "rb"))

    rows = []
    for label, cfg in CONFIGS:
        eq, expR, win = curve(h, l, c, trades, cfg)
        rows.append((label, eq, eq[-1], expR, win))
    rows.sort(key=lambda r: r[2], reverse=True)   # best final R first

    fig, ax = plt.subplots(figsize=(13, 8))
    cmap = plt.get_cmap("tab20")
    for i, (label, eq, fin, expR, win) in enumerate(rows):
        base = label.startswith("baseline")
        ax.plot(range(1, len(eq) + 1), eq,
                color="black" if base else cmap(i % 20),
                lw=2.6 if base else 1.5, ls="--" if base else "-", zorder=5 if base else 2,
                label=f"{label:<24} {fin:+6.0f}R  ({win:.0f}%w, {expR:+.3f})")
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_title(f"Trade-management sweep — cumulative R (constant $ risk/trade)  ·  "
                 f"NQ {START[:4]}–{END[:4]}, {len(trades)} base trades", fontsize=12)
    ax.set_xlabel("trade #"); ax.set_ylabel("cumulative R")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, loc="upper left", ncol=1, framealpha=0.9,
              prop={"family": "monospace"})
    fig.tight_layout()
    fig.savefig(OUT, dpi=130)
    print(f"wrote {OUT}\n")
    print(f"{'config':<26}{'finalR':>8}{'win%':>7}{'expR':>8}")
    print("-" * 49)
    for label, eq, fin, expR, win in rows:
        print(f"{label:<26}{fin:>8.0f}{win:>7.0f}{expR:>8.3f}")


if __name__ == "__main__":
    main()
