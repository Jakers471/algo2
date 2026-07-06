"""src.strategy.snapshot — build the Snapshot: the strategy's single contract.

Pipeline position: indicators (raw math) -> readings (facts) -> **snapshot** ->
score -> decide -> manage. `build_snapshot()` runs the raw indicators, hands their
output to the readings modules (which derive the facts we actually use), and
bundles every reading into ONE State object. The replay monitor and the strategy
both consume THIS — nothing downstream ever touches raw indicators.

Adding an indicator to the pipeline = add a `readings/` module + a field here.
That is ADDITIVE: existing consumers ignore new fields, so nothing downstream
breaks. Renaming/removing a field is the only breaking change.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from ..config import strategy_config
from ..indicators.sessions import session_instances
from ..indicators.volume import compute_volume
from ..indicators.volume_profile import compute_volume_profile
from .readings.structure import read_structure
from .readings.volume import read_volume
from .readings.volume_profile import read_volume_profile


@dataclass
class Snapshot:
    """Everything true at one bar (`asof`). THE CONTRACT between the pipeline and
    its consumers. Grow it by ADDING fields (one per reading) — never remove."""
    symbol: str
    tf: str
    asof: int                            # Unix seconds (UTC) of the current bar
    price: float                         # last close
    # --- readings (facts derived from raw indicators) ---
    volume_profile: dict | None = None   # forming session: session/poc/vah/val/volume
    volume: dict | None = None           # time-based: bar / rvol / delta (per-bar)
    structure: dict | None = None        # GRADE engine: state/strength/poc/vah/val

    def to_dict(self) -> dict:
        return asdict(self)


def build_snapshot(df: pd.DataFrame, symbol: str, tf: str) -> "Snapshot | None":
    """OHLCV slice (tz-aware UTC index, already trimmed to `asof`) -> Snapshot for
    its last bar. Runs each raw indicator once, hands it to the matching reading,
    then assembles. None if there are no bars."""
    if df is None or df.empty:
        return None

    asof = int(df.index[-1].value // 1_000_000_000)
    price = float(df["close"].iloc[-1])

    # [indicators] raw  ->  [readings] facts (reading knobs come from config)
    rcfg = strategy_config()["readings"]
    vp_reading = read_volume_profile(compute_volume_profile(df), asof)
    vol_reading = read_volume(compute_volume(df),
                              window=rcfg["volume_window"], fast=rcfg["volume_fast"])
    # STRUCTURE grades the CURRENT SESSION (the strategy's L1 anchor), not the whole
    # loaded window — grading thousands of bars collapses efficiency toward 0 (always
    # WHIPSAW). Fall back to the full slice only if no session has formed.
    insts = session_instances(df)
    sess_bars = df.iloc[insts[-1]["start_pos"]:insts[-1]["end_pos"] + 1] if insts else df
    structure_reading = read_structure(sess_bars)

    return Snapshot(
        symbol=symbol,
        tf=tf,
        asof=asof,
        price=price,
        volume_profile=vp_reading,
        volume=vol_reading,
        structure=structure_reading,
    )
