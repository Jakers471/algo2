"""experiments/engine/research/backtest_excursion.py — MAE / MFE analysis (cached).

Uses the SAME trade set as backtest_equity.py (imports its collect()), but the FIRST run
caches the collected trades to out/trades_cache_*.pkl so this and any later analysis run
instantly without re-grading 1m bars again. Then it computes, per trade:

  MFE (maximum favorable excursion) — the furthest price ran IN YOUR FAVOR, in R.
  MAE (maximum adverse excursion)   — the furthest price ran AGAINST you, in R (heat taken).

Two flavors, both reported:
  - to-exit (under the 2R hard-stop rule): MAE = heat a trade took before it resolved.
    Winners' MAE tells you how tight you could set the stop without killing winners.
  - full-window (entry -> session close, unmanaged): MFE = how far price COULD have gone.
    Compared to the 2R target -> is the target leaving money on the table?

Also splits long vs short. Read-only; frozen engine.

  python experiments/engine/research/backtest_excursion.py --start 2020-01-01
"""
import argparse
import os
import pickle
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ENGINE))
sys.path.insert(0, HERE)
sys.path.insert(0, ENGINE)
sys.path.insert(0, REPO)
from backtest_equity import collect, sim  # noqa: E402  (same trade set + management sim)
from anchors import session_anchors  # noqa: E402


def get_trades(start, sessions, bias_str):
    tag = f"{start}_{sessions}_{bias_str}"
    cache = os.path.join(ENGINE, "out", f"trades_cache_{tag}.pkl")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            print(f"loaded cached trades: {cache}")
            return pickle.load(f)
    d5 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_5m.parquet"))
    d5 = d5.loc[d5.index >= pd.Timestamp(start, tz="UTC")]
    spans = session_anchors(d5, 1_000_000)
    if sessions:
        spans = spans[-sessions:]
    d1 = pd.read_parquet(os.path.join(REPO, "data", "NQ", "NQ_1m.parquet"))
    d1 = d1.loc[d1.index >= d5.index[spans[0]["start"]]]
    trades = collect(d5, d1, spans, bias_str)
    with open(cache, "wb") as f:
        pickle.dump(trades, f)
    print(f"collected {len(trades)} trades, cached -> {cache}")
    return trades


def excursions(t):
    """Return (result_R@2R, mae_to_exit, mfe_to_exit, mfe_full) all in R (mae/heat as +)."""
    e = t["entry"]; risk = abs(e - t["stop"]); side = t["side"]
    h, l, c = t["h"], t["l"], t["c"]
    target = e + 2 * risk if side == "long" else e - 2 * risk
    stop = t["stop"]
    mae = mfe = 0.0
    res = None
    for k in range(len(c)):
        if side == "long":
            fav = (h[k] - e) / risk; adv = (e - l[k]) / risk
            mfe = max(mfe, fav); mae = max(mae, adv)
            if l[k] <= stop:
                res = -1.0; break
            if h[k] >= target:
                res = 2.0; break
        else:
            fav = (e - l[k]) / risk; adv = (h[k] - e) / risk
            mfe = max(mfe, fav); mae = max(mae, adv)
            if h[k] >= stop:
                res = -1.0; break
            if l[k] <= target:
                res = 2.0; break
    if res is None:
        res = (c[-1] - e) / risk * (1 if side == "long" else -1)
    # full-window favorable excursion (ignore exit, to session close)
    if side == "long":
        mfe_full = (h.max() - e) / risk
    else:
        mfe_full = (e - l.min()) / risk
    return res, mae, mfe, mfe_full


def pct(a, q):
    return float(np.quantile(a, q)) if len(a) else float("nan")


def report(name, arr):
    if not len(arr):
        print(f"  {name:<26} (none)"); return
    a = np.array(arr)
    print(f"  {name:<26} mean {a.mean():>5.2f}  median {np.median(a):>5.2f}  "
          f"p90 {pct(a,0.9):>5.2f}  max {a.max():>5.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--sessions", type=int, default=0)
    ap.add_argument("--bias_str", type=float, default=0.3)
    args = ap.parse_args()

    trades = get_trades(args.start, args.sessions, args.bias_str)
    rows = []
    for t in trades:
        res, mae, mfe, mfe_full = excursions(t)
        rows.append(dict(side=t["side"], res=res, mae=mae, mfe=mfe, mfe_full=mfe_full,
                         win=res > 0))
    df = pd.DataFrame(rows)

    print("=" * 74)
    print(f"  MAE / MFE  -  VA breakout, 2R hard-stop baseline   ({len(df)} trades)")
    print(f"  MAE = heat taken (R, +) before exit ; MFE = favorable run (R)")
    print("=" * 74)
    print(f"\n  long {int((df.side=='long').sum())}  |  short {int((df.side=='short').sum())}"
          f"   -   long win {df[df.side=='long'].win.mean():.0%}  short win {df[df.side=='short'].win.mean():.0%}")

    print("\n  MAE (adverse heat, R) - how far AGAINST before the trade resolved:")
    report("all trades", df.mae)
    report("WINNERS only", df[df.win].mae)
    report("losers only", df[~df.win].mae)

    print("\n  MFE to exit (R) - favorable run captured before exit:")
    report("all trades", df.mfe)
    print("\n  MFE full-window (R) - furthest price ran in favor to session close:")
    report("all trades", df.mfe_full)
    report("WINNERS only", df[df.win].mfe_full)
    print(f"\n  MFE_full >= 3R on {(df.mfe_full>=3).mean():.0%} of trades, >= 4R on {(df.mfe_full>=4).mean():.0%}"
          f"   (money left on the table above the 2R target)")

    # ---- PNG: winners-vs-losers MAE, and full MFE distribution vs 2R ----
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    bins = np.linspace(0, 3, 31)
    ax[0].hist(np.clip(df[df.win].mae, 0, 3), bins=bins, color="#1a9850", alpha=0.7, label="winners")
    ax[0].hist(np.clip(df[~df.win].mae, 0, 3), bins=bins, color="#d73027", alpha=0.55, label="losers")
    ax[0].axvline(pct(df[df.win].mae, 0.9), color="#1a7a3a", ls="--", lw=1.5,
                  label=f"winners' p90 = {pct(df[df.win].mae,0.9):.2f}R heat")
    ax[0].set_title("MAE - adverse heat before exit (winners vs losers)")
    ax[0].set_xlabel("MAE (R against)"); ax[0].legend(fontsize=9)

    ax[1].hist(np.clip(df.mfe_full, 0, 6), bins=np.linspace(0, 6, 31), color="#4575b4", alpha=0.8)
    ax[1].axvline(2, color="#1a9850", ls="--", lw=2, label="2R target")
    ax[1].axvline(df.mfe_full.median(), color="#000", ls=":", lw=1.5,
                  label=f"median MFE = {df.mfe_full.median():.2f}R")
    ax[1].set_title("MFE full-window - furthest favorable run to session close")
    ax[1].set_xlabel("MFE (R in favor)"); ax[1].legend(fontsize=9)
    fig.suptitle(f"Excursion analysis - VA breakout, NQ {args.start}+ ({len(df)} trades)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(ENGINE, "out", "backtest_excursion.png")
    fig.savefig(out, dpi=120)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
