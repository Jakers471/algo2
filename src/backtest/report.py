"""src.backtest.report — turn a runner result into an equity curve + printed stats.

A consumer of run_backtest()'s output (trades + equity). Separate from the runner so the
same trade log can feed equity / excursion / cost reports without re-running. PNG only;
no strategy logic here.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def print_stats(result: dict) -> None:
    s = result["stats"]
    print("=" * 60)
    print(f"  BACKTEST  {s['trades']} trades")
    print(f"  win {s['win_rate']*100:.0f}%  |  expectancy {s['expectancy']:+.2f}R  |  "
          f"total {s['total_R']:+.1f}R  |  maxDD {s['max_dd']:+.1f}R")
    print(f"  cost {s['cost_pts']:.2f} pt/round-turn (net of commission + slippage)")
    print("=" * 60)
    for t in result["trades"][:12]:
        print(f"  {t['date']} {t['session']:<6} {t['direction']:<5} "
              f"{t['reason']:<13} {t['R_net']:+.2f}R")
    if len(result["trades"]) > 12:
        print(f"  ... (+{len(result['trades'])-12} more)")


def equity_png(result: dict, out_path: str, title: str = "") -> str:
    eq = result["equity"]
    s = result["stats"]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(range(1, len(eq) + 1), eq, color="#1a9850", lw=1.9)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_title(title or f"Equity — {s['trades']} trades, {s['total_R']:+.0f}R net "
                          f"(exp {s['expectancy']:+.2f}, DD {s['max_dd']:.0f})", fontsize=12)
    ax.set_xlabel("trade #"); ax.set_ylabel("cumulative R (net of costs)")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=120)
    return out_path


if __name__ == "__main__":
    import argparse
    from .runner import run_backtest

    ap = argparse.ArgumentParser(description="Run the pipeline backtest + report.")
    ap.add_argument("--start", default="2024-12-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--sessions", type=int, default=0, help="cap to the last N sessions (0 = all in range)")
    ap.add_argument("--commission_rt", type=float, default=4.0)
    ap.add_argument("--slip_ticks", type=float, default=1.0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "experiments", "engine", "out", "pipeline_backtest.png"))
    args = ap.parse_args()

    res = run_backtest(start=args.start, end=args.end,
                       max_sessions=(args.sessions or None),
                       commission_rt=args.commission_rt, slip_ticks=args.slip_ticks,
                       progress=True)
    print_stats(res)
    print("\nwrote", equity_png(res, args.out))
