"""backtests/sim.py — fast local manage-rule simulator + sweep.

Generates base VA-breakout trades on the LOCAL 1m parquet using the SAME frozen math the
strategy/csverify use (lean/vabreakout/grade_lib.py), then replays each trade's 1-minute bar
path under different MANAGE rules (breakeven, stop tightness, trailing, target) so we can sweep
them in seconds and pick the config with the best expectancy BEFORE committing a slow QC run.

Everything is measured in R = the config's own initial stop distance, so configs are comparable
at constant $ risk per trade (tighter stop + more size = same $). Entry = resting-stop fill at
the VA edge (level fill); one trade per session (the strategy's first VA-break that fills).

    python backtests/sim.py                     # default window, curated sweep
    python backtests/sim.py --start 2021-01-01 --end 2025-01-01
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lean", "vabreakout"))
from grade_lib import (grade, find_consolidation, BIAS_STR, STATE_WINDOW,  # noqa: E402
                       MIN_LEN, MIN_BARS, DET_WINDOW)

DATA = os.path.join(REPO, "data", "NQ", "NQ_1m.parquet")
CACHE = os.path.join(HERE, "_sim_cache")
CHI_WINDOWS = [("Asia", 18 * 60, 3 * 60), ("London", 3 * 60, 8 * 60), ("NY", 8 * 60, 17 * 60)]


def session_of(minute_of_day: int):
    for name, s, e in CHI_WINDOWS:
        if (s <= e and s <= minute_of_day < e) or (s > e and (minute_of_day >= s or minute_of_day < e)):
            return name
    return None


# ---------------------------------------------------------------- load + states
def load(start, end):
    df = pd.read_parquet(DATA)
    df = df.loc[(df.index >= pd.Timestamp(start, tz="UTC")) & (df.index < pd.Timestamp(end, tz="UTC"))]
    df = df.tz_convert("America/Chicago")
    o, h, l, c, v = (df[k].to_numpy(float) for k in ["open", "high", "low", "close", "volume"])
    idx = df.index
    mod = (idx.hour * 60 + idx.minute).to_numpy()          # minute-of-day (Chicago)
    epoch = idx.view("int64") // 10**9                      # seconds, for gap detection
    return o, h, l, c, v, mod, epoch


def rolling_states(o, h, l, c, v):
    n = len(c); st = [None] * n; W = STATE_WINDOW
    t0 = time.time()
    for i in range(W, n):
        st[i] = grade(o[i - W:i + 1], h[i - W:i + 1], l[i - W:i + 1], c[i - W:i + 1], v[i - W:i + 1]).state
        if i % 200_000 == 0:
            print(f"  states {i}/{n}  ({time.time()-t0:.0f}s)", flush=True)
    return st


# ---------------------------------------------------------------- generate base trades
def decide_arm(strength, cons, price):
    if strength is None or not cons:
        return None
    vah, val = cons["vah"], cons["val"]
    if vah <= val:
        return None
    if strength >= BIAS_STR and price < vah:
        return {"direction": "long", "entry": vah, "vah": vah, "val": val}
    if strength <= -BIAS_STR and price > val:
        return {"direction": "short", "entry": val, "vah": vah, "val": val}
    return None


def generate_trades(o, h, l, c, v, mod, epoch, st):
    """One trade per session: the first armed VA-break that fills. Returns dicts with the
    entry index + session-end index (the bar path for the manage sim)."""
    n = len(c); trades = []; i = 0
    while i < n:
        if session_of(mod[i]) is None:
            i += 1; continue
        name = session_of(mod[i])
        b5, cur5, pending, filled = [], [], None, None
        k = i
        while k < n and session_of(mod[k]) == name and not (k > i and epoch[k] - epoch[k - 1] > 1800):
            cur5.append(k)
            is5 = (mod[k] % 5 == 4) or (k + 1 >= n) or (mod[k + 1] // 5 != mod[k] // 5)
            if is5:
                a = np.array(cur5)
                b5.append([o[cur5[0]], h[a].max(), l[a].min(), c[cur5[-1]], v[a].sum()])
                cur5 = []
                if filled is None and len(b5) >= MIN_BARS and k >= STATE_WINDOW + MIN_LEN:
                    s5 = np.array(b5, float)
                    strength = grade(s5[:, 0], s5[:, 1], s5[:, 2], s5[:, 3], s5[:, 4]).strength
                    lo = max(0, k - DET_WINDOW + 1)
                    cons = find_consolidation(st[lo:k + 1], o[lo:k + 1], h[lo:k + 1],
                                              l[lo:k + 1], c[lo:k + 1], v[lo:k + 1])
                    pending = decide_arm(strength, cons, c[k])
            if pending is not None and filled is None:
                lvl, d = pending["entry"], pending["direction"]
                if (h[k] >= lvl) if d == "long" else (l[k] <= lvl):
                    filled = dict(pending, entry_idx=k)
            k += 1
        end = k - 1
        if filled is not None and filled["entry_idx"] < end:
            va = abs(filled["vah"] - filled["val"])
            trades.append({"entry_idx": filled["entry_idx"], "end_idx": end,
                           "direction": filled["direction"], "entry": filled["entry"],
                           "vah": filled["vah"], "val": filled["val"],
                           "va_width": va, "va_pct": va / filled["entry"]})
        i = k
    return trades


# ---------------------------------------------------------------- manage simulation
def simulate(h, l, c, tr, cfg):
    """Replay bars (entry_idx+1 .. end_idx) under cfg -> (R, reason). R in units of the initial
    stop distance Rd. cfg keys: stop_mult, be_trigger, target_R, trail_R (any may be None)."""
    long = tr["direction"] == "long"
    entry, vaw = tr["entry"], tr["va_width"]
    Rd = cfg["stop_mult"] * vaw
    if Rd <= 0:
        return None
    stop = entry - Rd if long else entry + Rd
    target = None
    if cfg.get("target_R"):
        target = entry + cfg["target_R"] * Rd if long else entry - cfg["target_R"] * Rd
    peak = entry; be_done = False
    for k in range(tr["entry_idx"] + 1, tr["end_idx"] + 1):
        hi, lo = h[k], l[k]
        # (1) exits first, against the stop/target set on PRIOR bars (a stop moved this bar can't
        #     also be hit this bar — the correct convention, and fair to breakeven/trailing).
        hit_stop = lo <= stop if long else hi >= stop
        hit_tgt = (target is not None) and (hi >= target if long else lo <= target)
        if hit_stop:                                        # same-bar tie -> stop (conservative)
            return (stop - entry) / Rd * (1 if long else -1), "stop"
        if hit_tgt:
            return (target - entry) / Rd * (1 if long else -1), "target"
        # (2) THEN advance peak / breakeven / trail for subsequent bars
        peak = max(peak, hi) if long else min(peak, lo)
        if cfg.get("be_trigger") and not be_done:
            if ((peak - entry) >= cfg["be_trigger"] * Rd) if long else ((entry - peak) >= cfg["be_trigger"] * Rd):
                stop = entry; be_done = True
        if cfg.get("trail_R"):
            stop = max(stop, peak - cfg["trail_R"] * Rd) if long else min(stop, peak + cfg["trail_R"] * Rd)
    return (c[tr["end_idx"]] - entry) / Rd * (1 if long else -1), "session_close"


def stats(h, l, c, trades, cfg):
    Rs = []
    for tr in trades:
        r = simulate(h, l, c, tr, cfg)
        if r is not None:
            Rs.append(r[0])
    Rs = np.array(Rs)
    if len(Rs) == 0:
        return None
    wins = Rs > 0
    return {"n": len(Rs), "win%": round(100 * wins.mean(), 1),
            "expR": round(Rs.mean(), 3), "totR": round(Rs.sum(), 1),
            "avgW": round(Rs[wins].mean(), 2) if wins.any() else 0.0,
            "avgL": round(Rs[~wins].mean(), 2) if (~wins).any() else 0.0}


# ---------------------------------------------------------------- sweep
def curated_configs():
    return [
        ("baseline (stop=VA, target 2R)",        dict(stop_mult=1.0, be_trigger=None, target_R=2.0, trail_R=None)),
        ("+ breakeven 1.0R",                      dict(stop_mult=1.0, be_trigger=1.0, target_R=2.0, trail_R=None)),
        ("+ breakeven 0.5R",                      dict(stop_mult=1.0, be_trigger=0.5, target_R=2.0, trail_R=None)),
        ("tighter stop 0.7 (no BE)",              dict(stop_mult=0.7, be_trigger=None, target_R=2.0, trail_R=None)),
        ("tighter 0.7 + BE 0.5",                  dict(stop_mult=0.7, be_trigger=0.5, target_R=2.0, trail_R=None)),
        ("tighter 0.85 + BE 0.5",                 dict(stop_mult=0.85, be_trigger=0.5, target_R=2.0, trail_R=None)),
        ("BE 0.5 + trail 1R (no target)",         dict(stop_mult=1.0, be_trigger=0.5, target_R=None, trail_R=1.0)),
        ("YOUR combo: 0.7 + BE 0.5 + trail 1R",   dict(stop_mult=0.7, be_trigger=0.5, target_R=None, trail_R=1.0)),
        ("YOUR combo + target 3R cap",            dict(stop_mult=0.7, be_trigger=0.5, target_R=3.0, trail_R=1.0)),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2025-01-01")
    args = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    key = os.path.join(CACHE, f"trades_{args.start}_{args.end}.pkl")
    if os.path.exists(key):
        o, h, l, c, v, mod, epoch = load(args.start, args.end)
        trades = pickle.load(open(key, "rb"))
        print(f"loaded {len(trades)} cached base trades ({args.start}..{args.end})")
    else:
        print(f"loading 1m {args.start}..{args.end} ...")
        o, h, l, c, v, mod, epoch = load(args.start, args.end)
        print(f"  {len(c):,} 1m bars; grading rolling states (one-time) ...")
        st = rolling_states(o, h, l, c, v)
        print("  generating base trades ...")
        trades = generate_trades(o, h, l, c, v, mod, epoch, st)
        pickle.dump(trades, open(key, "wb"))
        print(f"  {len(trades)} base trades cached")

    va = np.array([t["va_pct"] for t in trades])
    cuts = {"all": 0.0, f">p33({np.quantile(va,.33)*100:.3f}%)": float(np.quantile(va, .33)),
            f">p50({np.quantile(va,.50)*100:.3f}%)": float(np.quantile(va, .50))}

    print(f"\nbase trades: {len(trades)}  |  VA-width %: "
          f"p25={np.quantile(va,.25)*100:.3f}%  median={np.median(va)*100:.3f}%  p75={np.quantile(va,.75)*100:.3f}%\n")
    print(f"{'config':<40}{'VA-filter':<16}{'n':>5}{'win%':>7}{'expR':>8}{'totR':>8}{'avgW':>7}{'avgL':>7}")
    print("-" * 108)
    for label, cfg in curated_configs():
        for cname, cut in cuts.items():
            sub = [t for t in trades if t["va_pct"] >= cut]
            s = stats(h, l, c, sub, cfg)
            if s:
                print(f"{label:<40}{cname:<16}{s['n']:>5}{s['win%']:>7}{s['expR']:>8}"
                      f"{s['totR']:>8}{s['avgW']:>7}{s['avgL']:>7}")
        print()


if __name__ == "__main__":
    main()
