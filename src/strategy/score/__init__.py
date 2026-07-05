"""src.strategy.score — facts -> weighted signals (OPINIONS). Tier 4.

The Score seam (`base.py`) + its versions (`v1.py`, …). Pick the active version in
config: `strategy.use.scorer`. readings=facts vs score=opinions stay separate.
"""
from .base import Scorer, Scores, get_scorer, register_scorer  # noqa: F401
from . import v1  # noqa: F401  — import so @register_scorer runs
