"""src.strategy.pipeline — wire the pipeline from config and run it on a Snapshot.

Reads `strategy.use.{scorer,decider,manager}` from algo_config.yaml, resolves the
chosen versions from each stage's registry, and runs snapshot -> score -> decide
-> manage. Swap a stage = change one word in config; this wiring never changes.

Right now score/decide/manage are stubs, so `run()` produces the live Snapshot
with empty scores / no intent / no action — the LEFT of the pipe (snapshot from
readings) is real; the RIGHT is scaffolded until Jake defines the logic.

TODO (STATE/MEMORY — do not forget when building `manage`): `run()` is currently
STATELESS per bar — it recomputes from the bars with no memory between calls. That
is correct for facts, but positions/decisions must PERSIST. When `manage` gets
logic, change this from stateless-per-bar to a driver that threads ONE persistent
`book` (open positions + armed intents + log) across bars — the same object in
replay/backtest/live (the brain's memory). See src/strategy/README.md "State &
memory".
"""
from __future__ import annotations

import pandas as pd

from ..config import strategy_config
from .decide import get_decider
from .manage import Book, get_manager
from .score import get_scorer
from .snapshot import build_snapshot


def run(df: pd.DataFrame, symbol: str, tf: str,
        ltf_df: pd.DataFrame | None = None, book: "Book | None" = None) -> dict:
    """OHLCV slice -> {snapshot, scores, intent, action, book} using the config's chosen
    stage versions. The one place the stages are wired together. `ltf_df` = optional
    finer-tf (1m) bars for the L2 reading. `book` = the persistent state threaded across
    bars (manage mutates it); pass the SAME book each bar (see Driver). A transient book
    is used if none is given — fine for a single-bar peek, wrong for a sequence."""
    if book is None:
        book = Book()
    snap = build_snapshot(df, symbol, tf, ltf_df=ltf_df)
    if snap is None:
        return {"snapshot": None, "scores": None, "intent": None, "action": None,
                "book": book.to_dict()}

    use = strategy_config()["use"]
    scores = get_scorer(use["scorer"]).score(snap)
    intent = get_decider(use["decider"]).decide(snap, scores)
    action = get_manager(use["manager"]).manage(intent, snap, book)

    return {
        "snapshot": snap.to_dict(),
        "scores": scores.to_dict(),
        "intent": intent.to_dict() if intent else None,
        "action": action.to_dict(),
        "book": book.to_dict(),
    }


class Driver:
    """Threads ONE persistent Book across bars — the brain's memory. Same object in
    replay / backtest / live. Feed it bars in order via step(); the book accumulates."""

    def __init__(self):
        self.book = Book()

    def step(self, df: pd.DataFrame, symbol: str, tf: str,
             ltf_df: pd.DataFrame | None = None) -> dict:
        return run(df, symbol, tf, ltf_df=ltf_df, book=self.book)
