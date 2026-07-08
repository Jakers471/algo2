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

Run:  python chart/server.py             (then open http://127.0.0.1:5000)
      python chart/server.py --restart   (stop an already-running one and take over)

Only ONE server per port: if one is already running, startup refuses (so you don't
stack duplicates) and points you at it — or `--restart` stops it and starts fresh. The
per-request access log is silenced so the terminal stays clean and Ctrl-C is easy.
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
from src.indicators.sessions import compute_sessions, session_instances  # noqa: E402
from src.indicators.volume_profile import compute_volume_profile  # noqa: E402
from src.indicators.range_hop import compute_range_hop  # noqa: E402  (TEMP experiment)
from src.indicators.volume import compute_volume  # noqa: E402
from src.indicators.moving_average import compute_moving_averages  # noqa: E402
from src.indicators.atr import compute_atr  # noqa: E402
from src.strategy import pipeline as strategy_pipeline  # noqa: E402

# Order timeframes coarse-to-fine for display; only those with a parquet show up.
TF_ORDER = ["1m", "5m", "15m", "60m", "1d"]

# Guard against path traversal in symbol/tf query params.
_SAFE = re.compile(r"^[A-Za-z0-9]+$")

app = Flask(__name__, static_folder="static", static_url_path="/static")
# Dev server: never let the browser cache anything, so a plain refresh (F5)
# always pulls the latest chart.html / JS / CSS — no hard-refresh needed.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# Silence Werkzeug's per-request log line. The chart fetches many indicators and the
# replay monitor polls 10x/s, so the default access log floods the terminal (and buries
# Ctrl-C). Errors/warnings still show; our own [replay] prints still show.
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ---- Replay state (chart -> terminal monitor) -----------------------------
# The chart's replay loop fire-and-forgets its cursor here; a standalone terminal
# monitor (tools/replay_monitor.py) polls it. In-memory + tiny so the browser
# push is near-free and never slows replay. The readout is computed lazily on the
# monitor's poll (off the browser loop) and cached per-asof.
_replay = {"active": False, "symbol": None, "tf": None, "asof": None}
_readout_cache = {}  # {(symbol, tf, asof): readout-or-None} — holds only latest

# The strategy is STATEFUL (manage owns a book across bars). We keep a persistent
# Driver and step it forward as the replay cursor advances — cheap (one bar/step).
# We only rebuild from the session start when the session changes or the cursor
# jumps BACKWARD (scrub); intraday positions never span sessions, so session start
# is a safe reset point. Guarded by a lock (Flask serves polls on threads).
import threading  # noqa: E402
_replay_lock = threading.Lock()
_replay_drv = {"driver": None, "sess_start": None, "asof": None, "result": None}


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
    result = compute_sessions(_asof_slice(_load_df(symbol, tf, limit)))
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


def _asof_slice(df):
    """For replay: if an `asof` (Unix seconds) param is present, keep only bars
    up to and including it — the same indicator math on a growing slice."""
    raw = request.args.get("asof")
    if raw is None:
        return df
    try:
        asof = int(raw)
    except ValueError:
        return df
    return df.loc[df.index <= pd.Timestamp(asof, unit="s", tz="UTC")]


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
        _asof_slice(_load_df(symbol, tf, limit)), row_size=row_size, value_area_pct=va
    )
    return jsonify(symbol=symbol, tf=tf, **result)


# --- TEMP/EXPERIMENTAL: connected session high/low lines + bias regime --------
# Per-session H/L (green up / red down) + bull/bear cloud from prior-session breaks.
@app.route("/api/indicators/range_hop")
def api_range_hop():
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    result = compute_range_hop(_asof_slice(_load_df(symbol, tf, limit)))
    return jsonify(symbol=symbol, tf=tf, **result)


@app.route("/api/indicators/volume")
def api_volume():
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    result = compute_volume(_asof_slice(_load_df(symbol, tf, limit)))
    return jsonify(symbol=symbol, tf=tf, **result)


@app.route("/api/indicators/moving_average")
def api_moving_average():
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    result = compute_moving_averages(_asof_slice(_load_df(symbol, tf, limit)))
    return jsonify(symbol=symbol, tf=tf, **result)


@app.route("/api/indicators/atr")
def api_atr():
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    result = compute_atr(_asof_slice(_load_df(symbol, tf, limit)))
    return jsonify(symbol=symbol, tf=tf, **result)


# ---- Strategy overlay (the pipeline drawn on the chart) --------------------
# Runs the WHOLE pipeline across a range in one batch (a fresh Driver stepped bar by
# bar — the same brain as replay/live) and returns the resulting trades + the base
# each entered on, as drawable data. This is the tune-and-see loop: edit a strategy
# knob in algo_config.yaml, refresh, and the overlay recomputes (cache is keyed by the
# config file's mtime, so a config edit invalidates it; an unchanged config is instant).
_strategy_cache = {"key": None, "result": None}


# Bounded trailing windows so per-bar work is CONSTANT, not growing with the range
# (the snapshot only needs the current session + the recent 1m window). Both comfortably
# exceed the longest session, so the snapshot is identical to feeding the full history.
_W5 = 300      # trailing 5m bars (~25h) — always contains the current session
_W1 = 900      # trailing 1m bars (~15h) — always contains the session's 1m bars


def _strategy_batch(symbol, tf, limit):
    """Step a Driver across the last `limit` bars -> {"trades": [...]}. Each trade is a
    CLOSED book entry enriched with the consolidation base captured at its entry bar.

    Uses bounded trailing 5m/1m windows and positional (searchsorted) 1m slicing so the
    cost is O(range), not O(range^2) — the full-slice version was ~35ms/bar (unusable)."""
    from src.strategy.readings.consolidation import clear_state_cache
    d5 = _load_df(symbol, tf, limit)
    d1 = _load_df(symbol, "1m", 200_000)
    d1_idx = d1.index                    # sorted -> searchsorted gives the cut in O(log n)
    clear_state_cache()
    drv = strategy_pipeline.Driver()
    bases_at = {}                       # opened_asof -> the base dict at entry
    idx = d5.index
    for i in range(len(d5)):
        t = idx[i]
        j = int(d1_idx.searchsorted(t, side="right"))     # # of 1m bars with index <= t
        w5 = d5.iloc[max(0, i - _W5 + 1):i + 1]
        w1 = d1.iloc[max(0, j - _W1):j]
        r = drv.step(w5, symbol, tf, ltf_df=w1)
        act = r.get("action") or {}
        if act.get("kind") == "activate":
            snap = r.get("snapshot") or {}
            bases_at[snap.get("asof")] = snap.get("consolidation") or {}
    trades = []
    for tr in drv.book.log:
        base = bases_at.get(tr.get("opened_asof")) or {}
        long = tr["direction"] == "long"
        trades.append({
            "direction": tr["direction"],
            "entry": tr["entry"], "exit": tr["exit"], "R": tr["R"], "reason": tr["reason"],
            "stop": tr["entry"] - tr["risk"] if long else tr["entry"] + tr["risk"],
            "entry_time": tr["opened_asof"], "exit_time": tr["closed_asof"],
            "base_vah": base.get("vah"), "base_val": base.get("val"),
            "base_start": base.get("start"), "base_end": base.get("end"),
        })
    return {"trades": trades}


@app.route("/api/strategy")
def api_strategy():
    """The strategy pipeline over a range, as drawable trades. Cached per
    (symbol, tf, limit, config-mtime) — recomputes only when the range or the config
    changes. Keep `limit` modest (the batch steps every bar); the renderer sends ~2500."""
    parsed = _request_params()
    if len(parsed) == 2:
        return parsed
    symbol, tf, limit = parsed
    try:
        mtime = os.path.getmtime(algo_config.CONFIG_PATH)
    except OSError:
        mtime = 0
    key = (symbol, tf, limit, mtime)
    if _strategy_cache["key"] != key:
        _strategy_cache["result"] = _strategy_batch(symbol, tf, limit)
        _strategy_cache["key"] = key
    return jsonify(symbol=symbol, tf=tf, **_strategy_cache["result"])


def _replay_pipeline():
    """Step the STATEFUL strategy pipeline to the replay `asof` and return
    {snapshot, scores, intent, action, book} — the same thing the strategy consumes;
    the terminal monitor renders it. Cached per-asof. A persistent Driver threads one
    `book` across bars: normally we just step forward the new bar(s); we rebuild from
    the session start on a session change or a backward scrub."""
    st = _replay
    if not (st["active"] and st["asof"] and st["symbol"] and st["tf"]):
        return None
    if not (_SAFE.match(str(st["symbol"])) and _SAFE.match(str(st["tf"]))):
        return None
    key = (st["symbol"], st["tf"], st["asof"])
    if key in _readout_cache:
        return _readout_cache[key]
    with _replay_lock:
        result = None
        try:
            asof_ts = pd.Timestamp(st["asof"], unit="s", tz="UTC")
            d5 = _load_df(st["symbol"], st["tf"], algo_config.chart_config()["limit"])
            d5 = d5.loc[d5.index <= asof_ts]
            if d5.empty:
                raise ValueError("no bars <= asof (cursor too early)")
            d1 = _load_df(st["symbol"], "1m", 120_000)          # wide 1m for the L2 reading
            insts = session_instances(d5)
            sess_start = d5.index[insts[-1]["start_pos"]] if insts else d5.index[0]
            rd = _replay_drv
            rebuild = (rd["driver"] is None or rd["sess_start"] != sess_start
                       or rd["asof"] is None or asof_ts < rd["asof"])
            if rebuild:
                from src.strategy.readings.consolidation import clear_state_cache
                clear_state_cache()             # bound the per-bar detection cache
                rd["driver"] = strategy_pipeline.Driver()
                rd["sess_start"] = sess_start
                bars = d5.index[(d5.index >= sess_start) & (d5.index <= asof_ts)]
            else:
                bars = d5.index[(d5.index > rd["asof"]) & (d5.index <= asof_ts)]
            # Bounded trailing windows (same as _strategy_batch) so each step is CONSTANT
            # work, not O(full slice): build_snapshot ran session_instances over the whole
            # growing 10k-bar slice per bar — the replay-poll slowdown. W5/W1 exceed the
            # longest session, so snapshots (and the book) are identical.
            d5_idx, d1_idx = d5.index, d1.index
            for t in bars:                                      # step the book forward
                p5 = int(d5_idx.searchsorted(t, side="right"))
                p1 = int(d1_idx.searchsorted(t, side="right"))
                rd["result"] = rd["driver"].step(
                    d5.iloc[max(0, p5 - _W5):p5], st["symbol"], st["tf"],
                    ltf_df=d1.iloc[max(0, p1 - _W1):p1])
            rd["asof"] = asof_ts
            result = rd["result"]
            if result is None or result.get("snapshot") is None:
                result = None
                if os.environ.get("REPLAY_DEBUG"):
                    print(f"[replay] snapshot None at asof {st['asof']} "
                          f"({len(d5)} bars) — cursor too early / no history yet", flush=True)
        except Exception:
            result = None
            # Never silently blank the monitor: surface WHY to the SERVER console.
            import traceback
            print(f"[replay] pipeline error at asof {st['asof']} ({st['symbol']} {st['tf']}):", flush=True)
            traceback.print_exc()
        _readout_cache.clear()  # keep only the latest asof
        _readout_cache[key] = result
        return result


@app.route("/api/replay/state", methods=["GET", "POST"])
def api_replay_state():
    """POST: the chart pushes its replay cursor {active, symbol, tf, asof}.
    GET: the terminal monitor polls current state + the pipeline result
    {snapshot, scores, intent, action}."""
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        _replay["active"] = bool(data.get("active", False))
        for k in ("symbol", "tf", "asof"):
            if k in data:
                _replay[k] = data[k]
        if not _replay["active"]:
            _replay["asof"] = None  # drop stale position on exit
        return ("", 204)
    resp = {k: _replay[k] for k in ("active", "symbol", "tf", "asof")}
    result = _replay_pipeline()
    if result:
        resp.update(result)  # snapshot, scores, intent, action
    return jsonify(resp)


def _port_in_use(port):
    """True if something is already listening on 127.0.0.1:<port>."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def _pids_on_port(port):
    """PIDs LISTENING on <port> (Windows: netstat; POSIX: lsof if present)."""
    import subprocess
    pids = set()
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pids.add(line.split()[-1])
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True).stdout
            pids.update(p for p in out.split() if p)
    except Exception:
        pass
    return pids


def _kill(pids):
    import subprocess
    for pid in pids:
        try:
            if sys.platform.startswith("win"):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(int(pid), 9)
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    import time as _time
    ap = argparse.ArgumentParser(description="volume_profile_algo chart server")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--restart", action="store_true",
                    help="if a server is already on the port, stop it and start fresh (no prompt)")
    args = ap.parse_args()

    # One server per port. If one's already up, don't silently stack a second — offer to
    # replace it (interactive), honor --restart, else refuse and point at the running one.
    if _port_in_use(args.port):
        pids = _pids_on_port(args.port)
        who = f" (PID {', '.join(sorted(pids))})" if pids else ""
        print(f"[!] A chart server is already running on http://127.0.0.1:{args.port}{who}")
        replace = args.restart
        if not replace and sys.stdin.isatty():
            try:
                replace = input("    Shut it down and restart here? [y/N] ").strip().lower() in ("y", "yes")
            except EOFError:
                replace = False        # no interactive input available -> don't stack a second
        if not replace:
            print(f"    Not starting a second one. Use the one at http://127.0.0.1:{args.port},")
            print("    or re-run with --restart to replace it.")
            sys.exit(1)
        _kill(pids)
        for _ in range(25):                       # wait for the port to actually free
            if not _port_in_use(args.port):
                break
            _time.sleep(0.2)
        print("    Old server stopped. Starting fresh...")

    # Hide Flask's " * Serving Flask app / Debug mode" banner — keep the terminal clean.
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None
    except Exception:
        pass
    print(f"[>] chart server: http://127.0.0.1:{args.port}   (Ctrl-C to stop)", flush=True)
    app.run(host="127.0.0.1", port=args.port, debug=False)
