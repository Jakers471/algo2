# experiments/har_vol — autoregressive volatility on NQ (HAR-RV)

An honest answer to "can we autoregress the NQ series?" — targeted at the part
that's actually forecastable: **volatility**, not price.

## Why volatility, not price
NQ price is a near-unit-root random walk. An AR on returns forecasts ~nothing
out-of-sample (efficient-market null) — that's the expected result, not a bug.
Volatility, by contrast, **clusters** (calm begets calm, storms beget storms), so
it carries real autoregressive memory. HAR-RV is the standard, hard-to-beat
baseline for it.

## The model — HAR-RV (Corsi 2009)
Tomorrow's realized volatility regressed on three autoregressive horizons:

    RVol_t = b0 + b_d·RVol_{t-1} + b_w·mean(RVol_{t-5..t-1}) + b_m·mean(RVol_{t-22..t-1})
                  \_ daily _/       \_ weekly _/                \_ monthly _/

"Realized vol" per day = sqrt of the sum of squared **intraday** log-returns
(overnight gaps excluded). Pure OLS, so walk-forward refit is cheap.

## Evaluation — strictly out-of-sample
Expanding-window walk-forward over the whole history: fit on the past, predict
the next day, never train on a point being scored. Reported against three naive
forecasts so the number means something:
- **RW** (`RVol_t = RVol_{t-1}`) — the honest bar; OOS R² is measured vs this.
- **weekly avg** and **RiskMetrics EWMA (λ=0.94)**.

## Files
- `har_rv.py` — the model + walk-forward. Needs the NQ parquets + pandas/numpy.
  ```
  python data/build_data.py                 # regenerate data/NQ/*.parquet first
  python experiments/har_vol/har_rv.py --tf 5m
  python experiments/har_vol/har_rv.py --tf 1m --min-train 750 --log --plot
  ```
  Prints an MSE/MAE/corr/R²-vs-RW table + fitted HAR coefficients; writes
  predictions to `out/` (+ a PNG with `--plot`).
- `verify_logic.py` — **pure stdlib** (no numpy/pandas/data). Reimplements the
  OLS + walk-forward on synthetic series to prove: OLS is correct, HAR detects
  real predictability, HAR does *not* fabricate skill on unpredictable data
  (anti-lookahead guard), and forecasts use past rows only. Run it anywhere:
  ```
  python experiments/har_vol/verify_logic.py
  ```

## What to expect on real NQ
Positive OOS R² vs random-walk (typically meaningful for daily RV), with the HAR
coefficients all positive and summing to <1 (persistent but mean-reverting vol).
That number = how much of NQ's day-to-day vol is genuinely predictable — a useful
input for sizing, stop distance, and regime gating in the signal pipeline.
