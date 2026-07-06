"""src.backtest.runner — the central backtester. Strategy-agnostic.

Drives the SAME pipeline Driver (src.strategy.pipeline) across history that replay and
live use, so a backtest cannot diverge from what you watch bar-by-bar. It knows nothing
about VA breakout — it just steps bars and reads the book's trade log. Swap the strategy
in algo_config.yaml (`strategy.use`) and this runs the new one unchanged.

Per session: a fresh Driver (positions are intraday, matching the replay's per-session
reset). Steps every bar; force-closes any open position at the session close. Then applies
a cost model (commission + slippage) per trade, in R vs that trade's own risk.

Perf: the pipeline rebuilds the snapshot each bar (1m rolling detection ~0.3s/bar), so this
is meant for bounded windows today; a fast path (precomputed rolling states) is a follow-up.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
from src.strategy.pipeline import Driver  # noqa: E402
from src.indicators.sessions import session_instances  # noqa: E402

POINT_VALUE = 20.0   # NQ E-mini $/point
TICK = 0.25          # index points per tick


def _parquet(symbol, tf):
    return os.path.join(_REPO, "data", symbol, f"{symbol}_{tf}.parquet")


def run_backtest(symbol="NQ", tf="5m", start="2024-12-01", end=None, max_sessions=None,
                 ltf_tf="1m", ltf_bars=200_000,
                 commission_rt=4.0, slip_ticks=1.0, progress=False) -> dict:
    """Step the Driver session-by-session over [start, end] -> trades + equity + stats.

    Costs (round turn): commission_rt $ + slip_ticks ticks/side -> fixed points, charged as
    R vs each trade's risk. Returns {trades, equity(list of cum R_net), stats, cost_pts}."""
    d5 = pd.read_parquet(_parquet(symbol, tf))
    d5 = d5.loc[d5.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        d5 = d5.loc[d5.index <= pd.Timestamp(end, tz="UTC")]
    d1 = pd.read_parquet(_parquet(symbol, ltf_tf)).tail(ltf_bars)

    insts = session_instances(d5, 10_000_000)
    if max_sessions:
        insts = insts[-max_sessions:]
    cost_pts = commission_rt / POINT_VALUE + slip_ticks * 2 * TICK

    trades = []
    for si, inst in enumerate(insts):
        if progress and si % 5 == 0:
            print(f"  session {si+1}/{len(insts)} ({d5.index[inst['start_pos']].date()}) "
                  f"trades={len(trades)}", flush=True)
        drv = Driver()
        idx = d5.index[inst["start_pos"]:inst["end_pos"] + 1]
        last_price = None
        for t in idx:
            r = drv.step(d5.loc[d5.index <= t], symbol, tf, ltf_df=d1.loc[d1.index <= t])
            if r["snapshot"]:
                last_price = r["snapshot"]["price"]
        # force-close any open position at the session close (intraday)
        pos = drv.book.position
        if pos is not None and last_price is not None:
            R = round((last_price - pos.entry) / pos.risk * (1 if pos.direction == "long" else -1), 2)
            drv.book.log.append({"direction": pos.direction, "entry": pos.entry, "exit": last_price,
                                 "risk": pos.risk, "R": R, "reason": "session_close",
                                 "opened_asof": pos.opened_asof, "closed_asof": int(idx[-1].value // 1_000_000_000)})
        for tr in drv.book.log:
            cost_R = cost_pts / tr["risk"] if tr.get("risk") else 0.0
            tr = dict(tr, session=inst["session"], date=str(d5.index[inst["start_pos"]].date()),
                      cost_R=round(cost_R, 3), R_net=round(tr["R"] - cost_R, 2))
            trades.append(tr)

    return _summarize(trades, cost_pts)


def _summarize(trades, cost_pts) -> dict:
    rs = [t["R_net"] for t in trades]
    equity, run, peak, mdd = [], 0.0, 0.0, 0.0
    for r in rs:
        run += r
        equity.append(round(run, 2))
        peak = max(peak, run)
        mdd = min(mdd, run - peak)
    n = len(rs)
    stats = {
        "trades": n,
        "win_rate": round(sum(r > 0 for r in rs) / n, 3) if n else 0.0,
        "expectancy": round(sum(rs) / n, 3) if n else 0.0,
        "total_R": round(sum(rs), 1),
        "max_dd": round(mdd, 1),
        "cost_pts": round(cost_pts, 2),
    }
    return {"trades": trades, "equity": equity, "stats": stats, "cost_pts": cost_pts}
