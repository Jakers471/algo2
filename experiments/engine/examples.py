"""experiments/engine/examples.py — example-session picker for the views/proofs.

NOT part of the frozen core. Just selects a contrasting set of NY sessions (strongest
bull/bear + two flattest) to demo and validate the engine on. Kept in the engine so the
views/proofs don't depend on the archived layer1/layer2 scripts.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
from src.indicators.sessions import session_instances  # noqa: E402


def pick_sessions(df5):
    """-> [((net_pct, start_ts, end_ts), label), ...] for 4 contrasting NY sessions."""
    ny = [s for s in session_instances(df5, 1_000_000) if s["session"] == "NY"]
    scored = []
    for s in ny:
        w = df5.iloc[s["start_pos"]:s["end_pos"] + 1]
        rng = float(w["high"].max() - w["low"].min()) or 1e-9
        netp = float(w["close"].iloc[-1] - w["open"].iloc[0]) / rng
        scored.append((netp, df5.index[s["start_pos"]], df5.index[s["end_pos"]]))
    scored.sort()
    flat = sorted(scored, key=lambda x: abs(x[0]))[:2]
    return [(scored[-1], "STRONGEST BULL"), (scored[0], "STRONGEST BEAR"),
            (flat[0], "FLATTEST (chop) #1"), (flat[1], "FLATTEST (chop) #2")]
