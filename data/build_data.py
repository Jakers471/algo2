"""
build_data — regenerate simplicity's clean parquets from the TradeStation source.

WHY: the old algoproj/NQdata intraday parquets have a corrupt volume column -- the
builder concatenated TradeStation's two volume columns (`Up`, `Down`) as text
("5"+"108"="5108") instead of summing. Real volume = Up + Down. See NOTES F1 / F4.

WHAT:
  NQ  (2005-2025, all TFs) -- the existing parquets have CORRECT timestamps + OHLC
      (verified row-for-row against the txt), so we keep them and only overwrite the
      volume column with the correctly-summed Up+Down (intraday) / Vol (daily).
  ES  (2005-2025) -- parsed fresh from es120.txt (1-min), timestamps are exchange
      (CENTRAL) time -> localized America/Chicago -> UTC (matches the NQ convention),
      volume = Up + Down, then resampled to 5m/15m/60m.

OUTPUT: simplicity/data/NQ_{1m,5m,15m,60m,1d}.parquet + ES_{1m,5m,15m,60m}.parquet
        (tz-aware UTC index, columns open/high/low/close/volume). Gitignored -- big;
        regenerate from source with this script.

Run:  python simplicity/data/build_data.py
"""
import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # simplicity/
import strategy_config as cfg

SRC = cfg.SOURCE_TXT_DIR
OLD_NQ = os.path.join(os.path.dirname(os.path.dirname(HERE)), "NQdata")  # algoproj/NQdata
NQ_OUT = os.path.join(HERE, "NQ"); os.makedirs(NQ_OUT, exist_ok=True)
ES_OUT = os.path.join(HERE, "ES"); os.makedirs(ES_OUT, exist_ok=True)

# NQ: tf -> (existing parquet, source txt, intraday?)
NQ = {
    "1m":  ("NQ_1min_clean.parquet",  "nq120.txt",    True),
    "5m":  ("NQ_5min_clean.parquet",  "nq520.txt",    True),
    "15m": ("NQ_15min_clean.parquet", "na1520.txt",   True),
    "60m": ("NQ_60min_clean.parquet", "nq6020.txt",   True),
    "1d":  ("NQ_1day_clean.parquet",  "nq1day20.txt", False),
}


def build_nq():
    for tf, (pq, txt, intra) in NQ.items():
        p = pd.read_parquet(os.path.join(OLD_NQ, pq))
        cols = ["Up", "Down"] if intra else ["Vol"]
        v = pd.read_csv(os.path.join(SRC, txt), usecols=cols)
        assert len(v) == len(p), f"{tf}: len mismatch {len(v)} vs {len(p)}"
        out = p[["open", "high", "low", "close"]].copy()
        out["volume"] = (v["Up"] + v["Down"]).to_numpy() if intra else v["Vol"].to_numpy()
        out.to_parquet(os.path.join(NQ_OUT, f"NQ_{tf}.parquet"))
        print(f"NQ_{tf:<3} {len(out):>9,} bars  vol/bar median {int(out['volume'].median()):>8,}  "
              f"max {int(out['volume'].max()):>10,}")


def _parse_ts(path, cols):
    """TradeStation txt -> tz-aware UTC OHLCV (exchange = Central time)."""
    d = pd.read_csv(os.path.join(SRC, path), usecols=["Date", "Time"] + cols)
    ts = pd.to_datetime(d["Date"] + " " + d["Time"], format="%m/%d/%Y %H:%M")
    idx = ts.dt.tz_localize("America/Chicago", ambiguous="infer",
                            nonexistent="shift_forward").dt.tz_convert("UTC")
    out = pd.DataFrame({
        "open": d["Open"].values, "high": d["High"].values,
        "low": d["Low"].values, "close": d["Close"].values,
        "volume": (d["Up"] + d["Down"]).values,
    }, index=idx).sort_index()
    out.index.name = "datetime"
    return out


def _resample(df, rule):
    o = df.resample(rule).agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last"),
                              volume=("volume", "sum")).dropna(subset=["open"])
    return o


def build_es():
    OHLCV = ["Open", "High", "Low", "Close", "Up", "Down"]
    es1 = _parse_ts("es120.txt", OHLCV)
    es1.to_parquet(os.path.join(ES_OUT, "ES_1m.parquet"))
    print(f"ES_1m  {len(es1):>9,} bars  {es1.index[0].date()}..{es1.index[-1].date()}")
    for tf, rule in [("5m", "5min"), ("15m", "15min"), ("60m", "60min")]:
        r = _resample(es1, rule)
        r.to_parquet(os.path.join(ES_OUT, f"ES_{tf}.parquet"))
        print(f"ES_{tf:<3} {len(r):>9,} bars (resampled)")


if __name__ == "__main__":
    print("building NQ (row-aligned volume fix)...")
    build_nq()
    print("\nbuilding ES (parsed + resampled from 1m)...")
    build_es()
    print("\ndone ->", HERE)
