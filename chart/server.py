"""
chart/server.py — Flask backend that connects the parquet data to the chart UI.

Serves the chart page + static assets and exposes a small JSON API:

  GET /                              -> chart.html
  GET /api/timeframes?symbol=NQ      -> {"symbol":"NQ","timeframes":["1m",...]}
  GET /api/candles?symbol=NQ&tf=5m   -> {"candles":[...], "volumes":[...]}

Candles/volumes are Lightweight-Charts-ready: `time` is a Unix timestamp in
seconds (UTC). By default the API returns the most recent LIMIT bars per
timeframe (10,000).

The chart is meant to be reusable, so this stays self-contained: it only reads
the parquets under <repo>/data/<SYMBOL>/<SYMBOL>_<tf>.parquet.

Run:  python chart/server.py   (then open http://127.0.0.1:5000)
"""
import os
import re
import functools

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(REPO_ROOT, "data")

# Show this many most-recent bars per timeframe.
DEFAULT_LIMIT = 10_000

# Order timeframes coarse-to-fine for display; only those with a parquet show up.
TF_ORDER = ["1m", "5m", "15m", "60m", "1d"]

# Guard against path traversal in symbol/tf query params.
_SAFE = re.compile(r"^[A-Za-z0-9]+$")

app = Flask(__name__, static_folder="static", static_url_path="/static")


def _parquet_path(symbol, tf):
    return os.path.join(DATA_DIR, symbol, f"{symbol}_{tf}.parquet")


def available_timeframes(symbol):
    return [tf for tf in TF_ORDER if os.path.exists(_parquet_path(symbol, tf))]


@functools.lru_cache(maxsize=32)
def _load_tail(symbol, tf, limit):
    """Load the last `limit` bars for (symbol, tf) as LWC-ready dicts. Cached:
    the parquets are static, so we only pay the read once per (symbol, tf)."""
    df = pd.read_parquet(_parquet_path(symbol, tf))
    df = df.tail(limit)

    # UTC index -> Unix seconds (int) for Lightweight Charts.
    times = (df.index.view("int64") // 1_000_000_000).tolist()

    candles = [
        {"time": t, "open": o, "high": h, "low": l, "close": c}
        for t, o, h, l, c in zip(
            times, df["open"], df["high"], df["low"], df["close"]
        )
    ]
    volumes = [
        {"time": t, "value": int(v)} for t, v in zip(times, df["volume"])
    ]
    return {"candles": candles, "volumes": volumes}


@app.route("/")
def index():
    return send_from_directory(HERE, "chart.html")


@app.route("/api/timeframes")
def api_timeframes():
    symbol = request.args.get("symbol", "NQ")
    if not _SAFE.match(symbol):
        return jsonify(error="bad symbol"), 400
    return jsonify(symbol=symbol, timeframes=available_timeframes(symbol))


@app.route("/api/candles")
def api_candles():
    symbol = request.args.get("symbol", "NQ")
    tf = request.args.get("tf", "5m")
    if not (_SAFE.match(symbol) and _SAFE.match(tf)):
        return jsonify(error="bad symbol/tf"), 400
    if not os.path.exists(_parquet_path(symbol, tf)):
        return jsonify(error=f"no data for {symbol} {tf}"), 404

    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except ValueError:
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, 200_000))

    payload = _load_tail(symbol, tf, limit)
    return jsonify(symbol=symbol, tf=tf, **payload)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
