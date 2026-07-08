"""src.config — loader for algo_config.yaml, the single source of truth for
every tunable knob (sessions, volume profile, chart defaults).

Read LIVE on each call (the file is tiny) so editing the YAML is reflected on the
next request — no restart. Everything numeric/parametric across the project
(indicators now; strategy + backtester later) resolves its knobs through here so
the chart and the backtests can't disagree.
"""
from __future__ import annotations

import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "algo_config.yaml")


def load() -> dict:
    """Parse algo_config.yaml fresh (so edits take effect without a restart)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _hhmm_to_min(value) -> int:
    """'18:00' -> 1080 (minutes from midnight)."""
    h, m = str(value).split(":")
    return int(h) * 60 + int(m)


def sessions_config() -> dict:
    """Resolved session config: windows as minutes-from-midnight + color.

    Returns {"timezone", "max_sessions", "windows": [{name,start,end,color}, ...]}
    preserving the order the windows appear in the YAML.
    """
    cfg = load().get("sessions", {})
    windows = []
    for name, w in (cfg.get("windows") or {}).items():
        windows.append({
            "name": name,
            "start": _hhmm_to_min(w["start"]),
            "end": _hhmm_to_min(w["end"]),
            "color": w.get("color", "#888888"),
        })
    return {
        "timezone": cfg.get("timezone", "America/Chicago"),
        "max_sessions": int(cfg.get("max_sessions", 60)),
        "windows": windows,
    }


def volume_profile_config() -> dict:
    cfg = load().get("volume_profile", {})
    return {
        "row_size": float(cfg.get("row_size", 5.0)),
        "value_area_pct": float(cfg.get("value_area_pct", 0.70)),
    }


def volume_config() -> dict:
    """Resolved volume (time-based histogram) config: bar colors + band height.

    Colors are a frontend concern (the math has no knobs); they live here so the
    chart's volume colors are config-driven like everything else.
    """
    cfg = load().get("volume", {})
    return {
        "up_color": cfg.get("up_color", "rgba(25, 158, 112, 0.5)"),
        "down_color": cfg.get("down_color", "rgba(230, 103, 103, 0.5)"),
        "height_pct": float(cfg.get("height_pct", 0.20)),
    }


def moving_averages_config() -> dict:
    """Resolved moving-average config: the price source + the ordered lines.

    Returns {"source", "lines": [{"period": int, "color": str}, ...]} preserving
    the order the lines appear in the YAML.
    """
    cfg = load().get("moving_averages", {})
    lines = []
    for ln in (cfg.get("lines") or []):
        kind = str(ln.get("type", "sma")).lower()
        lines.append({
            "type": kind if kind in ("sma", "ema") else "sma",
            "period": int(ln["period"]),
            "color": ln.get("color", "#888888"),
        })
    return {
        "source": str(cfg.get("source", "close")),
        "lines": lines,
    }


def atr_config() -> dict:
    """Resolved ATR (Average True Range) config: the smoothing `period`, the line
    `color`, and `height_pct` (how tall the lower band it docks in is).

    `period` is the only math knob (read by src.indicators.atr); color + height are
    presentation, read by the renderer, and live here so ATR is config-driven like
    every other indicator.
    """
    cfg = load().get("atr", {})
    return {
        "period": int(cfg.get("period", 14)),
        "color": cfg.get("color", "#eb6834"),
        "height_pct": float(cfg.get("height_pct", 0.18)),
    }


def strategy_config() -> dict:
    """Pipeline config: which VERSION of each stage runs (`use` slots) + the tunable
    knobs for each concern (`readings`, `regime`, `consolidation`, `decide`). Every
    numeric parameter the strategy runs on is resolved here from algo_config.yaml, so
    editing the YAML + refreshing changes the readings/regime/trades with no restart.

    Defaults equal the values previously hardcoded in the engine, so an unedited YAML
    reproduces the prior behaviour exactly (change a knob = change the output)."""
    cfg = load().get("strategy", {})
    use = cfg.get("use", {}) or {}
    readings = cfg.get("readings", {}) or {}
    regime = cfg.get("regime", {}) or {}
    consolidation = cfg.get("consolidation", {}) or {}
    decide = cfg.get("decide", {}) or {}
    return {
        "use": {
            "scorer": use.get("scorer", "v1"),
            "decider": use.get("decider", "va_breakout"),
            "manager": use.get("manager", "fixed"),
        },
        "readings": {
            "volume_window": int(readings.get("volume_window", 20)),
            "volume_fast": int(readings.get("volume_fast", 3)),
        },
        # regime — the GRADE state classifier's cutoffs (passed into grade()).
        "regime": {
            "n_rows": int(regime.get("n_rows", 24)),
            "e_cut": float(regime.get("e_cut", 0.38)),
            "a_cut": float(regime.get("a_cut", 0.55)),
            "min_bars": int(regime.get("min_bars", 8)),
        },
        # consolidation — the L2 leg-based base detector (breakout levels). Legs are
        # swing legs (threshold = swing_frac * session range); base_method selects how a
        # leg is judged a base (grade_state reuses the regime cutoffs; va_frac is the
        # archived value-area rule with its own va_thr).
        "consolidation": {
            "swing_frac": float(consolidation.get("swing_frac", 0.20)),
            "base_method": str(consolidation.get("base_method", "grade_state")),
            "va_thr": float(consolidation.get("va_thr", 0.55)),
            "min_leg_len": int(consolidation.get("min_leg_len", 5)),
            "max_age": int(consolidation.get("max_age", 40)),
        },
        # decide — the va_breakout entry rule.
        "decide": {
            "bias_str": float(decide.get("bias_str", 0.3)),
            "target_r": float(decide.get("target_r", 2.0)),
        },
    }


def chart_config() -> dict:
    cfg = load().get("chart", {})
    return {
        "symbol": cfg.get("symbol", "NQ"),
        "timeframe": cfg.get("timeframe", "5m"),
        "limit": int(cfg.get("limit", 10000)),
    }
