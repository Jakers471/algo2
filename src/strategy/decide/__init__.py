"""src.strategy.decide — scores -> trade Intent. Tier 5.

The Decide seam (`base.py`) + its versions (`v1.py`, …). Pick the active version in
config: `strategy.use.decider`.
"""
from .base import Decider, Intent, get_decider, register_decider  # noqa: F401
from . import v1  # noqa: F401  — import so @register_decider runs
