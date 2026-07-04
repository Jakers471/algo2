"""
chart/server.py — Flask backend that connects the parquet data to the chart UI.

This is the seam between the backend and the chart: it reads the parquets and
delegates all indicator math to `src/` (single source of truth), then serves the
results to the frontend. The JS just renders what it gets.

  GET /                                    -> chart.html
  GET /api/timeframes?symbol=NQ            -> {"symbol","timeframes":[...]}
  GET /api/candles?symbol=NQ&tf=5m         -> {"candles":[...], "volumes":[...]}
  GET /api/indicators/sessions?symbol=NQ&tf=5m
        -> {"sessions":[...], "rays":[...], "verticals":[...]}  (from src.indicators)

All `time` fields are Unix seconds (UTC). The API returns the most recent LIMIT
bars per timeframe (10,000) by default.

Run:  python chart/server.py   (then open http://127.0.0.1:5000)
"""
import os
import re
import sys
import functools

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(REPO_ROOT, "data")

# Make the backend (src/) importable — the chart is the frontend, src/ owns math.
sys.path.insert(0, REPO_ROOT)
from src import config as algo_config  # noqa: E402
from src.indicators.sessions import compute_sessions  # noqa: E402
from src.indicators.volume_profile import compute_volume_profile  # noqa: E402

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
def _load_df(symbol, tf, limit):
    """Last `limit` bars for (symbol, tf) as a DataFrame. Cached: the parquets
    are static, so we read once per (symbol, tf, limit). Callers must not mutate
    the returned frame."""
    return pd.read_parquet(_parquet_path(symbol, tf)).tail(limit)


def _load_tail(symbol, tf, limit):
    """LWC-ready candles/volumes for (symbol, tf)."""
    df = _load_df(symbol, tf, limit)

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


@app.route("/api/config")
def api_config():
    """The full algo_config.yaml as JSON — the frontend reads knobs (colors,
    row_size, defaults) from here so the chart reflects the config."""
    return jsonify(algo_config.load())


@app.route("/api/timeframes")
def api_timeframes():
    symbol = request.args.get("symbol", algo_config.chart_config()["symbol"])
    if not _SAFE.match(symbol):
        return jsonify(error="bad symbol"), 400
    return jsonify(symbol=symbol, timeframes=available_timeframes(symbol))


def _request_params():
    """Parse & validate symbol/tf/limit (defaults from config). Returns
    (symbol, tf, limit) or an (error_response, status) tuple to return directly."""
    ccfg = algo_config.chart_config()
    symbol = request.args.get("symbol", ccfg["symbol"])
    tf = request.args.get("tf", ccfg["timeframe"])
    if not (_SAFE.match(symbol) and _SAFE.match(tf)):
        return jsonify(error="bad symbol/tf"), 400
    if not os.path.exists(_parquet_path(symbol, tf)):
        return jsonify(error=f"no data for {symbol} {tf}"), 404
    try:
        limit = int(request.args.get("limit", ccfg["limit"]))
    except ValueError:
        limit = ccfg["limit"]
    return symbol, tf, max(1, min(limit, 200_000))


@app.route("/api/candles")
def api_candles():
    parsed = _request_params()
    if len(parsed) == 2:  # (response, status)
        return parsed
    symbol, tf, limit = parsed
    return jsonify(symbol=symbol, tf=tf, **_load_tail(symbol, tf, limit))


@app.route("/api/indicators/sessions")
def api_sessions():
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    result = compute_sessions(_load_df(symbol, tf, limit))
    return jsonify(symbol=symbol, tf=tf, **result)


def _opt_float(name):
    """Optional float query param; None if absent/invalid (-> compute uses config)."""
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@app.route("/api/indicators/volume_profile")
def api_volume_profile():
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    # Absent params -> compute_volume_profile falls back to algo_config.yaml.
    row_size = _opt_float("row_size")
    va = _opt_float("value_area_pct")
    result = compute_volume_profile(
        _load_df(symbol, tf, limit), row_size=row_size, value_area_pct=va
    )
    return jsonify(symbol=symbol, tf=tf, **result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
