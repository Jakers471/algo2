"""backtests/analyze.py — one run -> report.md + equity.png (+ append registry.csv).

Cross-engine: reads a run folder (NinjaTrader trades.csv OR QuantConnect trades.json),
normalizes to one canonical trade schema, and reports in the SAME vocabulary as
src/backtest/report.py so every engine's numbers line up. Nothing here is strategy math.

Usage:
    python backtests/analyze.py runs/<run_id>      # one run
    python backtests/analyze.py --all              # (re)analyze every run
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
REGISTRY = os.path.join(HERE, "registry.csv")
NQ_POINT = 20.0   # $ per NQ point (E-mini NASDAQ-100)

# ---------------------------------------------------------------- normalize
def _load_meta(run_dir: str) -> dict:
    p = os.path.join(run_dir, "meta.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def normalize(run_dir: str) -> pd.DataFrame:
    """Engine dump -> canonical columns:
       entry_time, exit_time, direction, entry, exit, stop, target,
       reason, pnl_points, pnl_currency, commission, mae_points, mfe_points, R.
    Missing columns come back as NaN (R/stop/target may be absent on older NT exports)."""
    csv, js = os.path.join(run_dir, "trades.csv"), os.path.join(run_dir, "trades.json")
    if os.path.exists(csv):
        r = pd.read_csv(csv)
        d = pd.DataFrame({
            "entry_time": pd.to_datetime(r.get("EntryTime"), errors="coerce"),
            "exit_time": pd.to_datetime(r.get("ExitTime"), errors="coerce"),
            "direction": r.get("Direction", "").astype(str).str.lower(),
            "entry": r.get("EntryPrice"), "exit": r.get("ExitPrice"),
            "stop": r.get("Stop"), "target": r.get("Target"),
            "reason": r.get("ExitName", "").astype(str),
            "pnl_points": r.get("ProfitPoints"), "pnl_currency": r.get("ProfitCurrency"),
            "commission": r.get("Commission", 0.0),
            "mae_points": r.get("MaePoints"), "mfe_points": r.get("MfePoints"),
            "R": r.get("R"),
        })
    elif os.path.exists(js):
        recs = json.load(open(js))
        r = pd.DataFrame(recs)
        sign = r["direction"].str.lower().map({"long": 1, "short": -1}).fillna(0)
        pts = (r["exit"] - r["entry"]) * sign
        d = pd.DataFrame({
            "entry_time": pd.to_datetime(r.get("time"), errors="coerce"),
            "exit_time": pd.to_datetime(r.get("time"), errors="coerce"),
            "direction": r["direction"].str.lower(),
            "entry": r["entry"], "exit": r["exit"],
            "stop": r.get("stop"), "target": r.get("target"),
            "reason": r.get("reason", "").astype(str),
            "pnl_points": pts, "pnl_currency": pts * NQ_POINT,
            "commission": 0.0, "mae_points": pd.NA, "mfe_points": pd.NA,
            "R": r.get("R"),
        })
    else:
        raise FileNotFoundError(f"no trades.csv or trades.json in {run_dir}")
    # infer R when stop is known but R wasn't exported
    if "R" not in d or d["R"].isna().all():
        risk = (d["entry"] - d["stop"]).abs()
        sign = d["direction"].map({"long": 1, "short": -1})
        d["R"] = ((d["exit"] - d["entry"]) * sign / risk).where(risk > 0)
    return d


def _reason_class(reason) -> str:
    r = str(reason).lower()
    if "target" in r or "profit" in r:
        return "target"
    if "stop" in r:
        return "stop"
    return "other"


# ---------------------------------------------------------------- stats
def stats(d: pd.DataFrame) -> dict:
    n = len(d)
    pts, cur, com = d["pnl_points"], d["pnl_currency"], d["commission"].fillna(0)
    net_cur = cur - com
    wins = pts > 0
    cls = d["reason"].map(_reason_class)
    brk = cls.isin(["stop", "target"])
    gross_win = cur[cur > 0].sum()
    gross_loss = -cur[cur < 0].sum()
    haveR = d["R"].notna().any()
    eq_r = d["R"].fillna(0).cumsum() if haveR else None
    eq_cur = net_cur.cumsum()
    def maxdd(series):
        return float((series - series.cummax()).min()) if len(series) else 0.0
    return {
        "trades": n,
        "win_rate": float(wins.mean()) if n else 0.0,
        "target_hit": float((cls[brk] == "target").mean()) if brk.any() else float("nan"),
        "expectancy_R": float(d["R"].mean()) if haveR else float("nan"),
        "total_R": float(d["R"].sum()) if haveR else float("nan"),
        "max_dd_R": maxdd(eq_r) if haveR else float("nan"),
        "profit_factor": float(gross_win / gross_loss) if gross_loss else float("inf"),
        "gross_currency": float(cur.sum()),
        "commission": float(com.sum()),
        "net_currency": float(net_cur.sum()),
        "max_dd_currency": maxdd(eq_cur),
        "avg_win_pts": float(pts[wins].mean()) if wins.any() else 0.0,
        "avg_loss_pts": float(pts[~wins].mean()) if (~wins).any() else 0.0,
        "exit_breakdown": d["reason"].value_counts().to_dict(),
        "date_start": str(d["entry_time"].min()), "date_end": str(d["entry_time"].max()),
        "dir_split": d["direction"].value_counts().to_dict(),
        "_have_R": haveR,
        "_eq_r": eq_r, "_eq_cur": eq_cur,
    }


# ---------------------------------------------------------------- outputs
def equity_png(s: dict, out_path: str, title: str) -> None:
    use_r = s["_have_R"]
    eq = (s["_eq_r"] if use_r else s["_eq_cur"]).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(range(1, len(eq) + 1), eq, color="#1a9850", lw=1.9)
    ax.axhline(0, color="#999", lw=0.8)
    ax.fill_between(range(1, len(eq) + 1), eq, 0, where=(eq >= 0), color="#1a9850", alpha=0.08)
    ax.set_title(title, fontsize=12)
    ax.set_xlabel("trade #")
    ax.set_ylabel("cumulative R" if use_r else "cumulative $ (net)")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _fmt(x, pct=False, sign=False):
    if isinstance(x, float) and (x != x):  # NaN
        return "n/a"
    if pct:
        return f"{x*100:.1f}%"
    if sign:
        return f"{x:+,.2f}"
    return f"{x:,.2f}" if isinstance(x, float) else str(x)


def report_md(run_id: str, meta: dict, s: dict, d: pd.DataFrame) -> str:
    L = [f"# {run_id}\n", "![equity](equity.png)\n", "## Label"]
    for k in ["platform", "bar_type", "tick_replay", "fill_resolution",
              "commission_per_rt", "slippage_ticks", "sample_type", "notes"]:
        if k in meta:
            L.append(f"- **{k}**: {meta[k]}")
    L += ["", "## Results",
          f"- **trades**: {s['trades']}  ({s['dir_split']})",
          f"- **actual range**: {s['date_start'][:10]} → {s['date_end'][:10]}",
          f"- **win rate**: {_fmt(s['win_rate'], pct=True)}   "
          f"(target-hit on brackets: {_fmt(s['target_hit'], pct=True)})",
          f"- **expectancy**: {_fmt(s['expectancy_R'], sign=True)} R   |   "
          f"**total**: {_fmt(s['total_R'], sign=True)} R   |   maxDD {_fmt(s['max_dd_R'])} R",
          f"- **net $**: {_fmt(s['net_currency'], sign=True)}   "
          f"(gross {_fmt(s['gross_currency'], sign=True)}, commission -{_fmt(s['commission'])})",
          f"- **profit factor**: {_fmt(s['profit_factor'])}   |   maxDD ${_fmt(s['max_dd_currency'])}",
          f"- **avg win / loss (pts)**: {_fmt(s['avg_win_pts'], sign=True)} / "
          f"{_fmt(s['avg_loss_pts'], sign=True)}",
          "", "## Exits"]
    for k, v in s["exit_breakdown"].items():
        L.append(f"- {k}: {v}")
    return "\n".join(L) + "\n"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=HERE, text=True).strip()
    except Exception:
        return "?"


def _update_registry(run_id: str, meta: dict, s: dict) -> None:
    row = {
        "run_id": run_id, "platform": meta.get("platform", "?"),
        "range": f"{s['date_start'][:10]}..{s['date_end'][:10]}",
        "trades": s["trades"], "win%": round(s["win_rate"] * 100, 1),
        "expectancy_R": round(s["expectancy_R"], 3) if s["_have_R"] else "",
        "total_R": round(s["total_R"], 1) if s["_have_R"] else "",
        "net$": round(s["net_currency"], 0),
        "tick_replay": meta.get("tick_replay", ""),
        "commission_rt": meta.get("commission_per_rt", ""),
        "sample_type": meta.get("sample_type", ""),
        "commit": _git_commit(),
        "analyzed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
    }
    df = pd.read_csv(REGISTRY) if os.path.exists(REGISTRY) else pd.DataFrame()
    df = df[df.get("run_id", pd.Series(dtype=str)) != run_id] if len(df) else df
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(REGISTRY, index=False)


def analyze(run_dir: str) -> dict:
    run_dir = os.path.abspath(run_dir)
    run_id = os.path.basename(run_dir)
    meta = _load_meta(run_dir)
    d = normalize(run_dir)
    s = stats(d)
    fill = meta.get("fill_resolution", "?")
    title = (f"{run_id}  —  {s['trades']} trades, win {_fmt(s['win_rate'], pct=True)}, "
             f"{'exp ' + _fmt(s['expectancy_R'], sign=True) + 'R' if s['_have_R'] else 'net $' + _fmt(s['net_currency'], sign=True)}"
             f"  [{fill} fills]")
    equity_png(s, os.path.join(run_dir, "equity.png"), title)
    open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8").write(report_md(run_id, meta, s, d))
    _update_registry(run_id, meta, s)
    print(f"[{run_id}] {s['trades']} trades  win {_fmt(s['win_rate'], pct=True)}  "
          f"exp {_fmt(s['expectancy_R'], sign=True)}R  net ${_fmt(s['net_currency'], sign=True)}  "
          f"-> report.md + equity.png")
    return s


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--all":
        for name in sorted(os.listdir(RUNS)):
            p = os.path.join(RUNS, name)
            if os.path.isdir(p):
                analyze(p)
    elif args:
        analyze(args[0])
    else:
        print(__doc__)
