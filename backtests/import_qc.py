"""backtests/import_qc.py — pull a QuantConnect trades JSON into a labeled run folder.

The LEAN algo (lean/vabreakout_cs/Main.cs) saves its trade list to ObjectStore as
`vabreakout_trades.json` — a list of {time,direction,entry,stop,target,exit,reason,R}.
Download that file from the QC backtest, point this at it, and it lands in
backtests/runs/<run_id>/ with trades.json + meta.json, then auto-analyzes (R included).

Usage:
    python backtests/import_qc.py <qc_trades.json> --fill second --sample out_of_sample \
        --commission 4.0 --slippage 1 --range 2009-01-01 2026-01-01 --notes "10yr honest"
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone

import pandas as pd

import analyze  # same folder

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
NQ_MULT = 20.0   # $ per NQ point (to convert QC's currency MAE/MFE back to points)
PARAMS = {"NRows": 24, "StateWindow": 25, "MinLen": 15, "MaxAge": 40, "DetWindow": 120,
          "MinBars": 8, "ECut": 0.38, "ACut": 0.55, "BiasStr": 0.3, "TargetR": 2.0}


def main():
    ap = argparse.ArgumentParser(description="Import a QuantConnect run into backtests/runs/ "
                                             "(our ObjectStore trades JSON [has R], or QC's results Trades CSV [no R]).")
    ap.add_argument("json_path", metavar="TRADES_FILE",
                    help="our vabreakout_trades.json (list w/ R) OR QC's *_trades.csv results export")
    ap.add_argument("--fill", default="second", choices=["tick", "second", "minute"],
                    help="fill resolution the QC run used (label)")
    ap.add_argument("--sample", default="full", choices=["full", "in_sample", "out_of_sample"])
    ap.add_argument("--commission", type=float, default=4.0)
    ap.add_argument("--slippage", type=float, default=1)
    ap.add_argument("--instrument", default="NQ")
    ap.add_argument("--range", nargs=2, metavar=("START", "END"), default=None)
    ap.add_argument("--notes", default="")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    src = args.json_path
    is_csv = src.lower().endswith(".csv")

    if is_csv:
        # QC's standard results Trades CSV (no stop/target -> no R, but win%/$/equity are exact).
        q = pd.read_csv(src)
        sign = q["Direction"].str.lower().map({"buy": 1, "sell": -1}).fillna(0)
        pts = (q["Exit Price"] - q["Entry Price"]) * sign
        qty = q.get("Quantity", 1)
        out = pd.DataFrame({
            "EntryTime": q["Entry Time"], "ExitTime": q["Exit Time"],
            "Direction": sign.map({1: "Long", -1: "Short"}),
            "EntryPrice": q["Entry Price"], "ExitPrice": q["Exit Price"],
            "ExitName": "", "ProfitPoints": pts, "ProfitCurrency": q["P&L"],
            "Commission": q.get("Fees", 0.0),
            "MaePoints": q.get("MAE", 0.0) / (NQ_MULT * qty), "MfePoints": q.get("MFE", 0.0) / (NQ_MULT * qty),
            "Stop": "", "Target": "", "R": "",
        })
        times = pd.to_datetime(out["EntryTime"], errors="coerce")
        n = len(out)
    else:
        recs = json.load(open(src))
        if not isinstance(recs, list) or not recs:
            raise SystemExit(f"expected a non-empty JSON list of trades, got {type(recs).__name__}")
        times = pd.to_datetime([r.get("time") for r in recs], errors="coerce")
        n = len(recs)

    y0, y1 = times.min().year, times.max().year
    run_id = args.run_id or (f"{datetime.now().strftime('%Y-%m-%d')}_qc_{args.fill}_"
                             f"{args.instrument}_{y0}-{y1}")

    run_dir = os.path.join(RUNS, run_id)
    os.makedirs(run_dir, exist_ok=True)
    if is_csv:
        out.to_csv(os.path.join(run_dir, "trades.csv"), index=False)   # canonical CSV analyze reads
    else:
        shutil.copyfile(src, os.path.join(run_dir, "trades.json"))

    meta = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": "quantconnect", "strategy": "VABreakout", "instrument": args.instrument,
        "bar_type": "Minute/1", "tick_replay": False, "fill_resolution": args.fill,
        "commission_per_rt": args.commission, "slippage_ticks": args.slippage,
        "requested_range": args.range or [str(times.min().date()), str(times.max().date())],
        "params": PARAMS, "sample_type": args.sample,
        "notes": args.notes or f"imported from {os.path.basename(src)}",
    }
    json.dump(meta, open(os.path.join(run_dir, "meta.json"), "w"), indent=2)

    print(f"imported {n} QC trades -> {run_dir}")
    analyze.analyze(run_dir)


if __name__ == "__main__":
    main()
