"""src.strategy — the trading pipeline (broker-agnostic).

One direction, each stage one job, each talking to the next only through a stable
contract (see CLAUDE.md convention #7):

    indicators (raw) -> readings (facts) -> snapshot (the contract)
        -> score (opinions) -> decide (intent) -> manage (actions)

`pipeline.run(df, symbol, tf)` wires the config-chosen stage versions and runs one
Snapshot through. Strategies never touch broker-specific code — orders go through
the broker interface (src.brokers.base.Broker).

Status: readings + snapshot are live (carrying the volume-profile numbers today);
score/decide/manage are seam-only stubs pending Jake's measurement/weight design.
"""
