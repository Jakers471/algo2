"""backtests/compare.py — put N runs side by side, flag when they're not comparable.

Reads the registry (analyze.py must have run on each) and prints a compact table. Warns when
runs differ in their cost/fill contract (commission / tick_replay), because a paper run and a
tick run are NOT apples-to-apples.

Usage:
    python backtests/compare.py                       # all runs
    python backtests/compare.py <run_id> <run_id> ... # just these
"""
from __future__ import annotations

import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "registry.csv")
COLS = ["run_id", "platform", "range", "trades", "win%", "expectancy_R", "net$",
        "tick_replay", "commission_rt", "sample_type"]


def main(ids):
    if not os.path.exists(REGISTRY):
        print("no registry yet — run analyze.py first")
        return
    df = pd.read_csv(REGISTRY)
    if ids:
        df = df[df["run_id"].isin(ids)]
    if df.empty:
        print("no matching runs")
        return
    show = df[COLS].copy()
    show["run_id"] = show["run_id"].str.slice(0, 44)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(show.to_string(index=False))

    # comparability warnings
    warns = []
    if df["tick_replay"].nunique() > 1:
        warns.append("mixed tick_replay (paper vs tick fills) - win% not directly comparable")
    if df["commission_rt"].nunique() > 1:
        warns.append("mixed commission - net$ not directly comparable (compare in R instead)")
    if df["expectancy_R"].isna().all() or (df["expectancy_R"].astype(str) == "").all():
        warns.append("no R on any run - add Stop/Target/R to exports for cost-agnostic comparison")
    if warns:
        print("\n[!] comparability:")
        for w in warns:
            print("   -", w)


if __name__ == "__main__":
    main(sys.argv[1:])
