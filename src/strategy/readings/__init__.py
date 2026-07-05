"""src.strategy.readings — turn raw indicator output into FACTS.

Each module reads ONE indicator's raw numbers and computes the strategy-relevant
readings (e.g. the forming session's POC/VAH/VAL from the volume profile).
Objective measurements only — opinions/weighting live in `score`. build_snapshot
(src.strategy.snapshot) collects every reading into the Snapshot.

Pipeline position: indicators (raw) -> **readings** (facts) -> snapshot -> ...
"""
