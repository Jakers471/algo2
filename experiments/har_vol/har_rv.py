#!/usr/bin/env python3
"""experiments/har_vol/har_rv.py — walk-forward HAR-RV volatility forecast on NQ.

An AUTOREGRESSIVE VOLATILITY model over the whole NQ history, evaluated strictly
out-of-sample. The model is HAR-RV (Corsi 2009): tomorrow's realized volatility
regressed on three autoregressive horizons — yesterday (daily), the past week,
and the past month:

    RVol_t = b0 + b_d*RVol_{t-1} + b_w*mean(RVol_{t-5..t-1}) + b_m*mean(RVol_{t-22..t-1})

WHY VOLATILITY, NOT PRICE
    Price is a near-unit-root random walk: an AR on returns forecasts ~nothing
    out-of-sample (efficient-market null). Volatility CLUSTERS, so it is
    genuinely forecastable. HAR-RV is the standard, hard-to-beat baseline. This
    script measures HOW MUCH of NQ's day-to-day vol is predictable and benchmarks
    HAR against naive forecasts (random-walk, weekly-average, RiskMetrics EWMA).

HONEST EVALUATION
    - Realized volatility is built from INTRADAY squared log-returns per session
      (overnight gaps excluded — the first return of each day is dropped).
    - Walk-forward: OLS is refit on an EXPANDING past-only window and predicts the
      NEXT day. No point is ever in its own training set — no lookahead.
    - Reported OOS R^2 is vs the random-walk baseline (RVol_t = RVol_{t-1}), the
      honest bar for "did the model add anything over 'tomorrow ~ today'."

DATA
    data/NQ/NQ_{tf}.parquet — tz-aware UTC OHLCV (open/high/low/close/volume).
    Build with `python data/build_data.py`. Not committed (gitignored).

DEPS: pandas, numpy, pyarrow (already in requirements.txt). matplotlib optional
      (only for --plot).

Run:
    python experiments/har_vol/har_rv.py --tf 5m
    python experiments/har_vol/har_rv.py --tf 1m --min-train 750 --log --plot
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


# ---- data -> daily realized volatility -----------------------------------
def daily_realized_vol(df: pd.DataFrame) -> pd.Series:
    """Intraday bars -> one realized-volatility number per calendar day.

    RVol_d = sqrt(sum of squared intraday log-returns on day d). Overnight is
    excluded by differencing WITHIN each day (first bar of a day has no return),
    so an overnight gap can't masquerade as intraday volatility.
    """
    close = df["close"].astype(float)
    day = df.index.normalize()                      # calendar day key (UTC)
    logc = np.log(close)
    ret = logc.groupby(day).diff()                  # NaN at each day's first bar
    rv = ret.pow(2).groupby(day).sum()              # realized variance per day
    rvol = np.sqrt(rv)
    rvol = rvol[rvol > 0]                            # drop empty/holiday days
    rvol.index = pd.to_datetime(rvol.index)
    return rvol.sort_index()


# ---- HAR design matrix ---------------------------------------------------
def har_features(rvol: pd.Series, use_log: bool):
    """Build (y, X) for HAR. X columns: [const, daily, weekly, monthly] lags.

    Every feature at row t uses ONLY information available through t-1 (strictly
    lagged rolling means), so the matrix itself carries no lookahead.
    """
    s = np.log(rvol) if use_log else rvol.copy()
    daily = s.shift(1)
    weekly = s.shift(1).rolling(5).mean()
    monthly = s.shift(1).rolling(22).mean()
    X = pd.DataFrame({"daily": daily, "weekly": weekly, "monthly": monthly})
    df = pd.concat([s.rename("y"), X], axis=1).dropna()
    y = df["y"].to_numpy()
    Xm = np.column_stack([np.ones(len(df)), df[["daily", "weekly", "monthly"]].to_numpy()])
    return y, Xm, df.index


def _ols(X, y):
    """OLS coefficients via least squares (returns beta vector)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


# ---- walk-forward --------------------------------------------------------
def walk_forward(y, X, min_train: int, refit_every: int):
    """Expanding-window OLS. Predict y[t] from a model fit on [0, t). Returns
    (pred, actual, first_index) aligned over the OOS region [min_train, n)."""
    n = len(y)
    pred = np.full(n, np.nan)
    beta = None
    for t in range(min_train, n):
        if beta is None or (t - min_train) % refit_every == 0:
            beta = _ols(X[:t], y[:t])               # past-only fit
        pred[t] = X[t] @ beta
    m = ~np.isnan(pred)
    return pred[m], y[m], np.flatnonzero(m)[0]


# ---- baselines & metrics -------------------------------------------------
def ewma_rvol(rvol: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics EWMA on realized variance -> forecast vol (shifted, causal)."""
    var = rvol.to_numpy() ** 2
    f = np.empty(len(var))
    f[0] = var[0]
    for i in range(1, len(var)):
        f[i] = lam * f[i - 1] + (1 - lam) * var[i - 1]   # uses only past
    return pd.Series(np.sqrt(f), index=rvol.index)


def scores(actual, pred):
    err = actual - pred
    mse = float(np.mean(err ** 2))
    mae = float(np.mean(np.abs(err)))
    corr = float(np.corrcoef(actual, pred)[0, 1]) if np.std(pred) > 0 else float("nan")
    return mse, mae, corr


def r2_vs(actual, pred, baseline_pred):
    """Out-of-sample R^2 against a baseline forecast (Campbell-Thompson style)."""
    sse = np.sum((actual - pred) ** 2)
    sse_b = np.sum((actual - baseline_pred) ** 2)
    return 1.0 - sse / sse_b if sse_b > 0 else float("nan")


# ---- main ----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Walk-forward HAR-RV volatility forecast on NQ.")
    ap.add_argument("--tf", default="5m", help="bar timeframe (1m/5m/15m/60m)")
    ap.add_argument("--instrument", default="NQ")
    ap.add_argument("--data-root", default=os.path.join(REPO, "data"))
    ap.add_argument("--min-train", type=int, default=500, help="days before first OOS forecast")
    ap.add_argument("--refit-every", type=int, default=21, help="refit cadence in days (1 = daily)")
    ap.add_argument("--log", action="store_true", help="model log-RVol (better-behaved tails)")
    ap.add_argument("--plot", action="store_true", help="save predicted-vs-actual plot")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()

    path = os.path.join(args.data_root, args.instrument, f"{args.instrument}_{args.tf}.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}\n  build it first: python data/build_data.py")

    df = pd.read_parquet(path)
    rvol = daily_realized_vol(df)
    print(f"{args.instrument} {args.tf}: {len(df):,} bars -> {len(rvol):,} trading days "
          f"({rvol.index[0].date()} .. {rvol.index[-1].date()})")

    y, X, idx = har_features(rvol, use_log=args.log)
    if len(y) <= args.min_train + 30:
        raise SystemExit(f"not enough days ({len(y)}) for min-train={args.min_train}")

    pred, actual, off = walk_forward(y, X, args.min_train, args.refit_every)
    oos_idx = idx[off: off + len(pred)]

    # Baselines, aligned to the identical OOS region. In modeled space:
    #   RW      = daily lag  (X[:,1])  -> "tomorrow ~ today"
    #   weekly  = weekly lag (X[:,2])
    rw = X[off: off + len(pred), 1]
    wk = X[off: off + len(pred), 2]
    # EWMA lives in RVol space; map to modeled space so R^2 is comparable.
    ew = ewma_rvol(rvol).reindex(oos_idx).to_numpy()
    ew = np.log(ew) if args.log else ew

    space = "log-RVol" if args.log else "RVol"
    print(f"\nWalk-forward OOS: {len(pred):,} days "
          f"({oos_idx[0].date()} .. {oos_idx[-1].date()}), modeled in {space}, "
          f"refit every {args.refit_every}d\n")

    rows = [
        ("HAR-RV",        pred),
        ("RW (t-1)",      rw),
        ("weekly avg",    wk),
        ("EWMA .94",      ew),
    ]
    print(f"  {'model':<12} {'MSE':>12} {'MAE':>10} {'corr':>7} {'R2 vs RW':>9}")
    print("  " + "-" * 54)
    for name, p in rows:
        mse, mae, corr = scores(actual, p)
        r2 = r2_vs(actual, p, rw)
        print(f"  {name:<12} {mse:>12.3e} {mae:>10.3e} {corr:>7.3f} {r2:>9.3f}")

    # Final fitted HAR coefficients (last expanding window) — interpretability.
    beta = _ols(X[:len(idx)], y)
    print(f"\n  HAR coefs  const {beta[0]:+.4f}  daily {beta[1]:+.3f}  "
          f"weekly {beta[2]:+.3f}  monthly {beta[3]:+.3f}  "
          f"(persistence sum {beta[1]+beta[2]+beta[3]:.3f})")

    os.makedirs(args.out, exist_ok=True)
    csv = os.path.join(args.out, f"har_{args.instrument}_{args.tf}{'_log' if args.log else ''}.csv")
    pd.DataFrame({"actual": actual, "har": pred, "rw": rw, "ewma": ew},
                 index=oos_idx).to_csv(csv)
    print(f"\n  wrote {csv}")

    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(13, 4))
            ax.plot(oos_idx, actual, lw=0.6, label="actual", color="0.3")
            ax.plot(oos_idx, pred, lw=0.6, label="HAR", color="C1", alpha=0.8)
            ax.set_title(f"{args.instrument} {args.tf} — HAR-RV walk-forward OOS ({space})")
            ax.legend(loc="upper right")
            png = csv.replace(".csv", ".png")
            fig.tight_layout(); fig.savefig(png, dpi=120)
            print(f"  wrote {png}")
        except ImportError:
            print("  (matplotlib not installed — skipped --plot)")


if __name__ == "__main__":
    main()
