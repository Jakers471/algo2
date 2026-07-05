"""src.strategy.readings.volume_profile — facts from the Volume Profile.

Reads the RAW volume-profile output (src.indicators.volume_profile) and derives
the numbers the strategy actually looks at: the forming session's key levels.
Facts only — no opinions (that's `score`'s job).
"""
from __future__ import annotations


def read_volume_profile(vp_raw: dict, asof: int) -> dict | None:
    """Raw `compute_volume_profile()` result + current bar time (`asof`, Unix s)
    -> the forming session's reading `{session, poc, vah, val, volume}`, or None
    if no session has formed yet.

    The forming session is the profile whose [start, end] contains `asof`; if the
    current bar sits between sessions we fall back to the most recent profile.
    """
    profs = (vp_raw or {}).get("profiles", [])
    if not profs:
        return None
    cur = next((p for p in profs if p["start"] <= asof <= p["end"]), None)
    if cur is None:
        cur = profs[-1]
    return {
        "session": cur["session"],
        "poc": cur["poc"],
        "vah": cur["vah"],
        "val": cur["val"],
        "volume": cur["total_volume"],
    }
