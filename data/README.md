# data/ — clean market data (regenerated, not committed)

Clean parquets built from the TradeStation source (`strategy_config.SOURCE_TXT_DIR`),
with **real volume = `Up` + `Down`** (the old parquets concatenated those columns as
text — see NOTES F1 / F4). Split by instrument:

- `NQ/` — `NQ_{1m,5m,15m,60m,1d}.parquet` (Nasdaq-100 e-mini, 2005–2025). NQ timestamps &
  OHLC are the verified originals; only the volume column was corrected.
- `ES/` — `ES_{1m,5m,15m,60m}.parquet` (S&P 500 e-mini, 2005–2025) — parsed from the 1-min
  source (exchange/Central time → UTC) and resampled. For future cross-instrument breadth/OOS.

All: tz-aware UTC index, columns `open/high/low/close/volume`.

**The parquets are gitignored** (too large for git). Regenerate any time:

    python data/build_data.py
