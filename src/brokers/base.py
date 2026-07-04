"""src.brokers.base — the standard broker interface.

Placeholder: defines the contract every broker adapter implements and the
strategy depends on. Kept minimal for now; fill in as the strategy's needs
become concrete (orders, positions, market data, account state).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Broker(ABC):
    """Standard interface the strategy calls. Adapters translate to a real API."""

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def get_price(self, symbol: str) -> float:
        ...

    @abstractmethod
    def place_order(self, symbol: str, side: str, qty: float, **kwargs):
        ...

    @abstractmethod
    def positions(self):
        ...
