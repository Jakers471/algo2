"""src.strategy.manage — intent -> lifecycle Actions. Tier 6.

The Manage seam (`base.py`) + its versions (`fixed.py`, `trailing.py`, …). Pick the
active version in config: `strategy.use.manager`. Actions are abstract verbs, not
broker calls — the strategy stays broker-agnostic (CLAUDE.md #4).
"""
from .base import Action, Manager, get_manager, register_manager  # noqa: F401
from .book import Book, Position  # noqa: F401
from . import fixed, trailing  # noqa: F401  — import so @register_manager runs
