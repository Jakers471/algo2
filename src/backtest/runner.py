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

import json
import os
import sys

import pandas as pd

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
from src.strategy.pipeline import Driver  # noqa: E402
from src.strategy.readings.consolidation import clear_state_cache  # noqa: E402
from src.indicators.sessions import session_instances  # noqa: E402


def _flatten(r: dict, session: str, date: str) -> dict:
    """One flat row = everything the pipeline saw + decided this bar (for saving)."""
    s = r.get("snapshot") or {}
    s5 = s.get("structure") or {}
    s1 = s.get("structure_ltf") or {}
    cn = s.get("consolidation") or {}
    vp = s.get("volume_profile") or {}
    vo = s.get("volume") or {}
    it = r.get("intent") or {}
    ac = r.get("action") or {}
    ad = ac.get("detail") or {}
    bk = r.get("book") or {}
    return {
        "asof": s.get("asof"), "date": date, "session": session,
        "price": s.get("price"), "high": s.get("high"), "low": s.get("low"),
        "s5_state": s5.get("state"), "s5_strength": s5.get("strength"),
        "s5_eff": s5.get("efficiency"), "s5_acc": s5.get("acceptance"),
        "s1_state": s1.get("state"), "s1_strength": s1.get("strength"),
        "s1_eff": s1.get("efficiency"), "s1_acc": s1.get("acceptance"),
        "cons_vah": cn.get("vah"), "cons_val": cn.get("val"),
        "cons_len": cn.get("len"), "cons_ago": cn.get("ended_ago"),
        "vp_poc": vp.get("poc"), "vp_vah": vp.get("vah"), "vp_val": vp.get("val"),
        "vol_bar": vo.get("bar"), "vol_rvol": vo.get("rvol"),
        "vol_vexp": vo.get("vexp"), "vol_delta": vo.get("delta"),
        "intent_dir": it.get("direction"), "intent_entry": it.get("entry"),
        "intent_stop": it.get("stop"), "intent_target": it.get("target"),
        "act_kind": ac.get("kind"), "act_R": ad.get("R"), "act_reason": ad.get("reason"),
        "act_unreal_R": ad.get("unreal_R"),
        "book_realized_R": bk.get("realized_R"), "book_closed": bk.get("closed"),
    }

POINT_VALUE = 20.0   # NQ E-mini $/point
TICK = 0.25          # index points per tick


def _parquet(symbol, tf):
    return os.path.join(_REPO, "data", symbol, f"{symbol}_{tf}.parquet")


def run_backtest(symbol="NQ", tf="5m", start="2024-12-01", end=None, max_sessions=None,
                 ltf_tf="1m", commission_rt=4.0, slip_ticks=1.0, progress=False, save_dir=None,
                 save_every=100) -> dict:
    """Step the Driver session-by-session over [start, end] -> trades + equity + stats.

    Costs (round turn): commission_rt $ + slip_ticks ticks/side -> fixed points, charged as
    R vs each trade's risk. If `save_dir` is set, persist EVERYTHING — every bar's snapshot +
    decision + action (bars.parquet), the closed trades (trades.parquet), stats + run meta
    (json) — so later scripts recompute/replot without re-running. Returns the result dict."""
    start_ts = pd.Timestamp(start, tz="UTC")
    d5 = pd.read_parquet(_parquet(symbol, tf))
    d5 = d5.loc[d5.index >= start_ts]
    if end:
        d5 = d5.loc[d5.index <= pd.Timestamp(end, tz="UTC")]
    # 1m over the SAME range (+2d lead so the first session has detection history).
    d1 = pd.read_parquet(_parquet(symbol, ltf_tf))
    d1 = d1.loc[d1.index >= start_ts - pd.Timedelta("2D")]

    insts = session_instances(d5, 10_000_000)
    if max_sessions:
        insts = insts[-max_sessions:]
    cost_pts = commission_rt / POINT_VALUE + slip_ticks * 2 * TICK
    meta = {"symbol": symbol, "tf": tf, "start": start, "end": end,
            "sessions": len(insts), "commission_rt": commission_rt,
            "slip_ticks": slip_ticks, "cost_pts": round(cost_pts, 3)}

    trades, bars = [], []
    for si, inst in enumerate(insts):
        if progress and si % 10 == 0:
            print(f"  session {si+1}/{len(insts)} ({d5.index[inst['start_pos']].date()}) "
                  f"trades={len(trades)}", flush=True)
        clear_state_cache()                      # per-session: bound the perf cache
        drv = Driver()
        p0, p1 = inst["start_pos"], inst["end_pos"]
        buf = max(0, p0 - 40)                     # buffer for the readings' lookbacks (vol=20)
        date = str(d5.index[p0].date())
        last_price = None
        for bp in range(p0, p1 + 1):
            t = d5.index[bp]
            # Bounded windows: build_snapshot only ever needs the CURRENT session (+ a small
            # lookback), so this yields the IDENTICAL snapshot as passing the whole df — it
            # just keeps per-bar cost constant instead of growing with the backtest.
            win5 = d5.iloc[buf:bp + 1]
            win1 = d1.loc[d1.index <= t].tail(300)
            r = drv.step(win5, symbol, tf, ltf_df=win1)
            if r["snapshot"]:
                last_price = r["snapshot"]["price"]
            if save_dir is not None:
                bars.append(_flatten(r, inst["session"], date))
        # force-close any open position at the session close (intraday)
        pos = drv.book.position
        if pos is not None and last_price is not None:
            R = round((last_price - pos.entry) / pos.risk * (1 if pos.direction == "long" else -1), 2)
            drv.book.log.append({"direction": pos.direction, "entry": pos.entry, "exit": last_price,
                                 "risk": pos.risk, "R": R, "reason": "session_close",
                                 "opened_asof": pos.opened_asof, "closed_asof": int(d5.index[p1].value // 1_000_000_000)})
        for tr in drv.book.log:
            cost_R = cost_pts / tr["risk"] if tr.get("risk") else 0.0
            tr = dict(tr, session=inst["session"], date=date,
                      cost_R=round(cost_R, 3), R_net=round(tr["R"] - cost_R, 2))
            trades.append(tr)
        # incremental checkpoint: a long overnight run can be interrupted without losing everything
        if save_dir is not None and (si + 1) % save_every == 0:
            _save(save_dir, _summarize(trades, cost_pts), bars, dict(meta, sessions_done=si + 1))

    result = _summarize(trades, cost_pts)
    if save_dir is not None:
        _save(save_dir, result, bars, dict(meta, sessions_done=len(insts)))
    return result


def _save(save_dir, result, bars, meta) -> None:
    """Persist the full run: bars stream + trades + stats + meta."""
    os.makedirs(save_dir, exist_ok=True)
    pd.DataFrame(bars).to_parquet(os.path.join(save_dir, "bars.parquet"))
    pd.DataFrame(result["trades"]).to_parquet(os.path.join(save_dir, "trades.parquet"))
    with open(os.path.join(save_dir, "stats.json"), "w") as f:
        json.dump(result["stats"], f, indent=2)
    with open(os.path.join(save_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  saved: bars({len(bars)}) + trades({len(result['trades'])}) + stats + meta "
          f"-> {save_dir}", flush=True)


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
