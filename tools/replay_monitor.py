#!/usr/bin/env python3
"""tools/replay_monitor.py — live readout of the chart's replay, in a terminal.

Run alongside the chart server (`python chart/server.py`). It polls
`/api/replay/state`; when you hit **Replay** in the chart it streams the strategy
pipeline for each bar as replay steps forward, and prints `replay ended` on exit.

PURE READER — never drives the chart, so it can't slow replay. The chart
fire-and-forgets its cursor to the server; the server runs the pipeline
(src.strategy: snapshot → score → decide → manage — the single source of truth)
when we poll and returns {snapshot, scores, intent, action}.

VIEWS (pick with --view; same data, different layout):
  horizontal  a bucketed grid — one boxed column-group per phase, one row per bar,
              each value inline-labeled (px/POC/vol/conv/…) so a row reads on its
              own (the snapshot table extended rightward through the pipeline). DEFAULT.
  vertical    a 'funnel' block per bar — phases stacked top→bottom.
  snapshot    just the SNAPSHOT facts table (no pipeline columns).

PHASE PALETTE (consistent across views): SNAPSHOT=cyan · SCORE=yellow ·
DECIDE=magenta · MANAGE=blue. It tints each phase's borders/gutter+label so a
phase is the same color everywhere. Value colors are semantic (POC yellow,
VAH green / VAL red, conviction green once it clears threshold, dir/setup
green-long/red-short, stop red / target green).

NOTE: score/decide/manage are stubs today, so their cells are empty (`—`) until
those phases get logic — the layout is already in place, ready to light up.

Usage:
    python tools/replay_monitor.py                     # horizontal (default)
    python tools/replay_monitor.py --view vertical
    python tools/replay_monitor.py --view snapshot --hz 10 --no-color
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---- ANSI ----------------------------------------------------------------
R = "\033[0m"
_COLOR = True


def c(s, code):
    return f"\033[{code}m{s}{R}" if _COLOR else str(s)


WHT, GRAY, DIM = "1", "90", "2"
YEL, GRN, RED = "33", "32", "31"
# Phase identity colors (borders / gutters / labels) — consistent across views.
# The SNAPSHOT facts split into per-SOURCE boxes (PRICE / PROFILE / VOLUME) that
# share the cyan family (they're all facts); the pipeline phases differ.
PHASE_C = {"PRICE": "96", "PROFILE": "96", "VOLUME": "96",
           "STRUCT 5m": "96", "STRUCT 1m": "96", "CONSOL": "96", "SNAPSHOT": "96",
           "SCORE": "93", "DECIDE": "95", "MANAGE": "94"}
SESS_C = {"Asia": "94", "London": "93", "NY": "95"}


# ---- formatting ----------------------------------------------------------
def fmt_when(asof) -> str:
    """Unix seconds -> 'Mon D H:MM AM/PM' in UTC (matches the chart's clock)."""
    d = datetime.fromtimestamp(asof, tz=timezone.utc)
    h = d.hour % 12 or 12
    ampm = "AM" if d.hour < 12 else "PM"
    return f"{d.strftime('%b')} {d.day} {h}:{d.minute:02d} {ampm}"


def lvl(p) -> str:
    """Round a price level to the nearest 0.25 (like the chart)."""
    if p is None:
        return ""
    return f"{round(float(p) * 4) / 4:g}"


def short_vol(v) -> str:
    if v is None:
        return ""
    v = float(v)
    if v >= 1e6:
        return f"{v / 1e6:.2f}m"
    if v >= 1e3:
        return f"{round(v / 1e3)}k"
    return str(round(v))


def signed_vol(v) -> str:
    """Signed short volume for the delta, e.g. +45k / -12k."""
    if v is None:
        return ""
    return ("+" if v >= 0 else "-") + short_vol(abs(v))


# ---- pipeline fields -----------------------------------------------------
def _parts(st):
    snap = st.get("snapshot") or {}
    return (snap, snap.get("volume_profile") or {}, st.get("scores") or {},
            st.get("intent"), st.get("action") or {})


def _sig(sigs, key):
    return f"{sigs[key]:.2f}" if key in sigs else ""


# ---- table structure (phases -> columns) shared by horizontal/snapshot ----
# Each column is (inline_label, value_width, align). The label is printed dim next
# to the value on every row (e.g. "px 21915.5"), so a row reads without the header;
# "" = no label (self-evident cells: time, session, direction, setup, state).
# SNAPSHOT facts are split into boxes BY SOURCE: PRICE (the bar), PROFILE (from the
# volume-profile indicator), VOLUME (from the time-based volume indicator). Add a
# new reading → add a box here.
PHASES = [
    ("PRICE",    [("", 15, "<"), ("px", 8, ">")]),
    ("PROFILE",  [("", 6, "<"), ("POC", 7, ">"), ("VAH", 7, ">"), ("VAL", 7, ">"), ("vol", 5, ">")]),
    ("VOLUME",   [("bar", 5, ">"), ("rvol", 4, ">"), ("vexp", 4, ">"), ("Δ", 6, ">")]),
    ("STRUCT 5m",[("", 13, "<"), ("str", 5, ">"), ("eff", 4, ">"), ("acc", 4, ">")]),
    ("STRUCT 1m",[("", 13, "<"), ("str", 5, ">"), ("eff", 4, ">"), ("acc", 4, ">")]),
    ("CONSOL",   [("", 7, ">"), ("", 7, ">"), ("len", 3, ">"), ("ago", 3, ">")]),
    ("DECIDE",   [("", 5, "<"), ("entry", 8, ">"), ("stop", 8, ">"), ("tgt", 8, ">")]),
    ("MANAGE",   [("", 22, "<")]),
]

# The fact boxes (left of the pipeline stages) — used by the 'snapshot' view.
FACT_PHASES = 6


def _struct_cells(stc):
    """One GRADE structure box (state / str / eff / acc) — shared by both scales."""
    stc = stc or {}
    state = stc.get("state", "")
    scol = (GRN if state.endswith("UP") else RED if state.endswith("DN")
            else YEL if state == "CONSOLIDATION" else DIM)       # regime tint
    strg = stc.get("strength")
    return [(state, scol),
            (f"{strg:+.2f}" if strg is not None else "",
             GRN if (strg or 0) > 0 else RED if (strg or 0) < 0 else DIM),  # bias sign
            (f"{stc['efficiency']:.2f}" if "efficiency" in stc else "", WHT),
            (f"{stc['acceptance']:.2f}" if "acceptance" in stc else "", WHT)]


def _phase_cells(name, st):
    """(value, color) list for one phase's columns, from the pipeline result."""
    snap, vp, sc, intent, action = _parts(st)
    if name == "PRICE":                                          # the bar itself
        return [(fmt_when(st["asof"]), WHT), (lvl(snap.get("price")), WHT)]
    if name == "PROFILE":                                        # volume-profile indicator
        sess = vp.get("session", "")
        return [(sess, SESS_C.get(sess, DIM)), (lvl(vp.get("poc")), YEL),
                (lvl(vp.get("vah")), GRN), (lvl(vp.get("val")), RED),
                (short_vol(vp.get("volume")), DIM)]              # session cumulative
    if name == "VOLUME":                                         # time-based volume indicator
        vr = snap.get("volume") or {}
        d, up = vr.get("delta"), vr.get("up")
        return [(short_vol(vr.get("bar")),
                 GRN if up is True else RED if up is False else DIM),      # bull/bear tint
                (f"{vr['rvol']:.1f}" if "rvol" in vr else "", WHT),        # relative volume
                (f"{vr['vexp']:.1f}" if "vexp" in vr else "", WHT),        # volume expansion
                (signed_vol(d), GRN if (d or 0) >= 0 else RED)]            # recent delta
    if name == "STRUCT 5m":                                      # GRADE @ L1 (5m session)
        return _struct_cells(snap.get("structure"))
    if name == "STRUCT 1m":                                      # GRADE @ L2 (recent 1m) — fractal
        return _struct_cells(snap.get("structure_ltf"))
    if name == "CONSOL":                                         # L2 tradeable base (fact)
        cn = snap.get("consolidation") or {}
        if not cn:
            return [("", GRN), ("", RED), ("", DIM), ("", DIM)]  # no base right now
        return [(lvl(cn.get("vah")), GRN), (lvl(cn.get("val")), RED),   # VAH green / VAL red
                (str(cn.get("len", "")), DIM), (str(cn.get("ended_ago", "")), DIM)]
    if name == "SCORE":
        conv = sc.get("conviction", 0.0)
        sigs = sc.get("signals") or {}
        d = sc.get("direction")
        return [(f"{conv:.2f}", GRN if conv >= 0.60 else WHT), (_sig(sigs, "trend"), DIM),
                (_sig(sigs, "breakout"), DIM), (_sig(sigs, "location"), DIM),
                (d or "", GRN if d == "long" else RED if d == "short" else DIM)]
    if name == "DECIDE":
        if intent:
            d = intent.get("direction")
            return [(d.upper() if d else "", GRN if d == "long" else RED),
                    (lvl(intent.get("entry")), WHT), (lvl(intent.get("stop")), RED),
                    (lvl(intent.get("target")), GRN)]
        return [("—", DIM), ("", WHT), ("", WHT), ("", WHT)]
    # MANAGE — the trade lifecycle (from the book)
    kind = action.get("kind") or "none"
    d = action.get("detail") or {}
    dr = (d.get("direction") or "").upper()
    if kind == "activate":
        return [(f"{dr} entered", GRN)]
    if kind == "active":
        u = d.get("unreal_R", 0.0)
        return [(f"{dr} hold {u:+.1f}R", GRN if u >= 0 else RED)]
    if kind == "exit":
        R = d.get("R", 0.0)
        return [(f"exit {d.get('reason','')} {R:+.1f}R", GRN if R > 0 else RED)]
    return [("—", DIM)]


# ---- horizontal / snapshot (bucketed grid) -------------------------------
def _cw(label, w):
    """Display width of a cell = 'label ' prefix (if any) + value width."""
    return (len(label) + 1 if label else 0) + w


def _inner(cols):
    return sum(_cw(l, w) for l, w, _ in cols) + (len(cols) - 1)


def _cells(pairs, cols):
    """One bucket's cells. Labeled cells read 'label value' (label dim, left-
    aligned, padded right to keep the column width); blank values hide the label
    but keep the width. Unlabeled cells use the column's own alignment."""
    out = []
    for (val, code), (label, w, a) in zip(pairs, cols):
        cw = _cw(label, w)
        sval = str(val)
        if label and sval != "":
            pad = " " * max(0, cw - (len(label) + 1 + len(sval)))
            out.append(c(label, DIM) + " " + c(sval, code) + pad)
        elif label:
            out.append(" " * cw)  # blank cell, width preserved
        else:
            out.append(c(format(sval, f"{a}{w}"), code))
    return " ".join(out)


def _assemble(bucket_strs, phases):
    out = ""
    for (name, _), bs in zip(phases, bucket_strs):
        out += c("┊", PHASE_C[name]) + bs
    return out + c("┊", GRAY)


def top_border(phases):
    out = ""
    for i, (name, cols) in enumerate(phases):
        j = "┌" if i == 0 else "┬"
        w = _inner(cols)
        lbl = f"─ {name} "
        out += c(j, PHASE_C[name]) + c(lbl + "─" * (w - len(lbl)), PHASE_C[name])
    return out + c("┐", GRAY)


def rule(phases, left, mid, right):
    out = ""
    for i, (name, cols) in enumerate(phases):
        out += c(left if i == 0 else mid, PHASE_C[name]) + c("─" * _inner(cols), GRAY)
    return out + c(right, GRAY)


def data_row(st, phases):
    return _assemble([_cells(_phase_cells(name, st), cols) for name, cols in phases], phases)


# ---- vertical (funnel block) ---------------------------------------------
def funnel(st):
    snap, vp, sc, intent, action = _parts(st)
    sym, tf = snap.get("symbol", ""), snap.get("tf", "")
    when = fmt_when(st["asof"])
    W = 64
    pad = " " * max(1, W - len(when) - len(sym) - len(tf) - 8)
    head = f"{c('◆', GRAY)} {c(when, WHT)}{pad}{c(f'{sym} · {tf}', GRAY)}"

    def row(gutter, phase, body):
        col = PHASE_C[phase]
        return f"{c(gutter, col)} {c(phase.ljust(8), col)} {body}"

    sess = vp.get("session", "")
    vr = snap.get("volume") or {}
    px_txt = c("px " + lvl(snap.get("price")), WHT)
    if vp:
        sess_block = (f"   {c(sess, SESS_C.get(sess, DIM))} · POC {c(lvl(vp.get('poc')), YEL)} · "
                      f"VAH {c(lvl(vp.get('vah')), GRN)} · VAL {c(lvl(vp.get('val')), RED)} · "
                      f"{c('vol ' + short_vol(vp.get('volume')), DIM)}")
    else:
        sess_block = "   " + c("no session yet", DIM)
    if vr:
        dd = vr.get("delta")
        _bc = GRN if vr.get("up") is True else RED if vr.get("up") is False else DIM
        vol_txt = ("   " + c("bar " + short_vol(vr.get("bar")), _bc) + " · "
                   + c("rvol %.1f" % vr["rvol"], WHT) + " · "
                   + c("vexp %.1f" % vr["vexp"], WHT) + " · "
                   + c("Δ " + signed_vol(dd), GRN if (dd or 0) >= 0 else RED))
    else:
        vol_txt = ""
    s_body = px_txt + sess_block + vol_txt

    conv = sc.get("conviction", 0.0)
    sigs = sc.get("signals") or {}
    d = sc.get("direction")
    parts = [p for p in (
        f"trend {_sig(sigs, 'trend')}" if "trend" in sigs else "",
        f"breakout {_sig(sigs, 'breakout')}" if "breakout" in sigs else "",
        f"location {_sig(sigs, 'location')}" if "location" in sigs else "",
    ) if p]
    sig_txt = c(" · ".join(parts), DIM) if parts else c("no signals yet", DIM)
    dir_txt = c(d, GRN if d == "long" else RED) + " · " if d else ""
    sc_body = f"{c('conv %.2f' % conv, GRN if conv >= 0.60 else WHT)}   {dir_txt}{sig_txt}"

    if intent:
        di = intent.get("direction")
        d_body = (f"{c(di.upper() if di else '', GRN if di == 'long' else RED)} · "
                  f"entry {c(lvl(intent.get('entry')), WHT)} · stop {c(lvl(intent.get('stop')), RED)} · "
                  f"target {c(lvl(intent.get('target')), GRN)}")
    else:
        d_body = c("— no setup —", DIM)

    kind = action.get("kind") or ""
    m_body = c("flat" if kind in ("", "none") else kind,
               {"arm": YEL, "activate": GRN, "exit": RED}.get(kind, DIM))

    return "\n".join([head,
                      row("│", "SNAPSHOT", s_body),
                      row("│", "SCORE", sc_body),
                      row("│", "DECIDE", d_body),
                      row("╰", "MANAGE", m_body)])


# ---- polling -------------------------------------------------------------
def fetch(endpoint):
    """Poll the endpoint. Returns the JSON dict, or None for a connection error
    (server truly down) vs. False for a timeout/slow response (server busy — e.g.
    rebuilding the pipeline from a session start). The caller treats those differently
    so a slow bar isn't misreported as 'unreachable'."""
    try:
        # Generous timeout: a session-rebuild poll steps many bars (leg detection +
        # grades) and can take several seconds — that's busy, not down.
        with urllib.request.urlopen(endpoint, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        # Connection refused / name resolution -> down. Timeout -> busy.
        reason = getattr(e, "reason", None)
        if isinstance(reason, TimeoutError) or isinstance(e, urllib.error.HTTPError):
            return False
        return None
    except (TimeoutError, ConnectionError):
        return False
    except Exception:
        return None


def _enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


def _legend() -> str:
    """A guide to what every output column/field means (printed by --legend)."""
    rows = [
        ("time", "bar time (UTC) — the as-of moment in replay"),
        ("px", "price = the bar's close"),
        ("SESS", "active session (Asia / London / NY)"),
        ("POC", "Point of Control — most-traded price this session"),
        ("VAH", "Value-Area High — top of the value zone (value_area_pct of volume)"),
        ("VAL", "Value-Area Low — bottom of the value zone"),
        ("vol", "session cumulative volume so far"),
        ("bar", "this bar's traded volume — tinted green (up bar) / red (down bar)"),
        ("rvol", "relative volume = bar ÷ avg(last N bars); >1 = above average / spike"),
        ("vexp", "volume expansion = avg(fast bars) ÷ avg(N bars); rising = ramping up"),
        ("Δ", "delta = net signed volume over last N bars (+ buying / − selling)"),
        ("state", "GRADE regime — IMPULSE/GRIND (±dir) / CONSOLIDATION / WHIPSAW / UNCLEAR"),
        ("str", "strength = net ÷ range (−1..+1); the session-bias number (+ up / − down)"),
        ("eff", "efficiency = |net| ÷ travel (0..1); how direct the path (progress axis)"),
        ("acc", "acceptance = 1 − value-area fraction; fat POC reads high (acceptance axis)"),
        ("CONSOL", "L2 tradeable base: VAH (green) / VAL (red) breakout levels · len bars · ago = bars since it ended"),
    ]
    out = [c("FIELDS", "1") + c("  — what each output shows", DIM), "",
           c("SNAPSHOT", PHASE_C["SNAPSHOT"]) + c(" facts — boxed BY SOURCE: ", DIM) +
           c("PRICE", PHASE_C["PRICE"]) + c(" (the bar) · ", DIM) +
           c("PROFILE", PHASE_C["PROFILE"]) + c(" (volume-profile) · ", DIM) +
           c("VOLUME", PHASE_C["VOLUME"]) + c(" (time-based volume) · ", DIM) +
           c("STRUCT 5m/1m", PHASE_C["STRUCT 5m"]) + c(" (GRADE engine, L1 session + L2 1m — fractal) · ", DIM) +
           c("CONSOL", PHASE_C["CONSOL"]) + c(" (the 1m base)", DIM)]
    for k, v in rows:
        out.append("  " + c(k.ljust(6), WHT) + " " + c(v, DIM))
    out += ["",
            (c("DECIDE", PHASE_C["DECIDE"]) + c(" · ", DIM) + c("MANAGE", PHASE_C["MANAGE"]) +
             c("  pipeline stages", DIM)),
            "  " + c("DECIDE", WHT) + c(" the VA-breakout Intent — direction + entry / stop / target", DIM),
            "  " + c("MANAGE", WHT) + c(" trade state (arm / active / exit) — stub until phase 3", DIM),
            "",
            c("  SCORE stage is hidden", DIM) + c(" — VA-breakout is a rule, not a weighted-signal system, so it", DIM),
            c("  scores nothing. The slot stays in the pipeline for future confluence scoring.", DIM)]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Terminal readout of chart replay.")
    ap.add_argument("--url", default="http://127.0.0.1:5000", help="chart server base URL")
    ap.add_argument("--hz", type=float, default=10.0, help="polls per second")
    ap.add_argument("--view", choices=("horizontal", "vertical", "snapshot"),
                    default="horizontal", help="layout")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    ap.add_argument("--legend", action="store_true", help="print the field guide and exit")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    global _COLOR
    _COLOR = (not args.no_color) and sys.stdout.isatty()
    if _COLOR:
        _enable_ansi()

    if args.legend:
        print(_legend())
        return

    phases = PHASES if args.view == "horizontal" else PHASES[:FACT_PHASES] if args.view == "snapshot" else None
    is_table = args.view in ("horizontal", "snapshot")

    endpoint = args.url.rstrip("/") + "/api/replay/state"
    period = 1.0 / max(1.0, args.hz)

    print(f"replay_monitor · {args.view} · watching {endpoint}")
    print("  (run with --legend for a field guide · --view vertical|horizontal|snapshot) · waiting for replay…")
    was_active = last_asof = None
    was_active = False
    warned_down = False
    misses = 0
    MISS_LIMIT = 4          # consecutive connection failures before we call it "down"

    while True:
        st = fetch(endpoint)
        if st is False:
            # Busy/slow poll (server is mid-compute, e.g. rebuilding from a session
            # start). NOT a disconnect — skip this tick quietly, keep replay state.
            time.sleep(period)
            continue
        if st is None:
            misses += 1
            if misses >= MISS_LIMIT and not warned_down:
                print("… server unreachable (is chart/server.py running?)")
                warned_down = True
            time.sleep(0.5)
            continue
        if warned_down:
            print("… reconnected")
        warned_down = False
        misses = 0

        active = bool(st.get("active"))
        if active and not was_active:
            print("\n── replay initialised ──")
            if is_table:
                print(top_border(phases))
                print(rule(phases, "├", "┼", "┤"))
            last_asof = None
        elif not active and was_active:
            if is_table:
                print(rule(phases, "└", "┴", "┘"))
            print("── replay ended ──\n")
        was_active = active

        if active:
            asof = st.get("asof")
            if asof is not None and asof != last_asof:
                last_asof = asof
                if args.view == "vertical":
                    print(funnel(st))
                    print()
                else:
                    print(data_row(st, phases))

        time.sleep(period)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
