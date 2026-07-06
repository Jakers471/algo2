"""src.strategy.decide — scores -> trade Intent. Tier 5.

The Decide seam (`base.py`) + its versions (`va_breakout.py`, …). Pick the active
version in config: `strategy.use.decider`.
"""
from .base import Decider, Intent, get_decider, register_decider  # noqa: F401
from . import va_breakout  # noqa: F401  — import so @register_decider runs
