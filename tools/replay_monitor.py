#!/usr/bin/env python3
"""tools/replay_monitor.py — live readout of the chart's replay, in a terminal.

Run this alongside the chart server (`python chart/server.py`). It polls
`/api/replay/state`; when you hit **Replay** in the chart it prints
`replay initialised`, then streams the forming session's readout
(`when · session · POC · VAH · VAL · vol`) as replay steps forward, and prints
`replay ended` when you exit.

It is a PURE READER — it never drives the chart, so it can't slow replay. The
chart fire-and-forgets its cursor to the server; the server computes the readout
(reusing src/indicators, the single source of truth) when we poll.

Usage:
    python tools/replay_monitor.py
    python tools/replay_monitor.py --url http://127.0.0.1:5000 --hz 10
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone


def fetch(endpoint: str):
    """GET the replay state as a dict, or None if the server is unreachable."""
    try:
        with urllib.request.urlopen(endpoint, timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def fmt_when(asof: int) -> str:
    """Unix seconds -> 'Mon D H:MM AM/PM' in UTC (matches the chart's clock)."""
    d = datetime.fromtimestamp(asof, tz=timezone.utc)
    h = d.hour % 12 or 12
    ampm = "AM" if d.hour < 12 else "PM"
    return f"{d.strftime('%b')} {d.day} {h}:{d.minute:02d} {ampm}"


def lvl(p) -> str:
    """Round a price level to the nearest 0.25 (like the chart)."""
    return f"{round(float(p) * 4) / 4:g}"


def short_vol(v) -> str:
    v = float(v)
    if v >= 1e6:
        return f"{v / 1e6:.2f}m"
    if v >= 1e3:
        return f"{round(v / 1e3)}k"
    return str(round(v))


def readout_line(st: dict) -> str:
    when = fmt_when(st["asof"])
    if not st.get("session"):
        return when  # replay active but the session hasn't formed yet
    return (
        f"{when} · {st['session']} · POC {lvl(st['poc'])} · "
        f"VAH {lvl(st['vah'])} · VAL {lvl(st['val'])} · vol {short_vol(st['vol'])}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Terminal readout of chart replay.")
    ap.add_argument("--url", default="http://127.0.0.1:5000", help="chart server base URL")
    ap.add_argument("--hz", type=float, default=10.0, help="polls per second")
    args = ap.parse_args()

    # Emit UTF-8 so the '·' / '──' glyphs print (or at worst degrade) instead of
    # raising UnicodeEncodeError on a legacy Windows console codepage.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    endpoint = args.url.rstrip("/") + "/api/replay/state"
    period = 1.0 / max(1.0, args.hz)

    print(f"replay_monitor · watching {endpoint} · waiting for replay…")
    was_active = False
    last_asof = None
    warned_down = False

    while True:
        st = fetch(endpoint)
        if st is None:
            if not warned_down:
                print("… server unreachable (is chart/server.py running?)")
                warned_down = True
            time.sleep(0.5)
            continue
        warned_down = False

        active = bool(st.get("active"))
        if active and not was_active:
            print("── replay initialised ──")
            last_asof = None
        elif not active and was_active:
            print("── replay ended ──")
        was_active = active

        if active:
            asof = st.get("asof")
            if asof is not None and asof != last_asof:
                last_asof = asof
                print(readout_line(st))

        time.sleep(period)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()  # clean newline on Ctrl+C
