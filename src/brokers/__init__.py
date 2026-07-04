"""src.brokers — broker abstraction layer + per-broker adapters.

The strategy calls ONE standard interface (see base.py). Each supported broker
gets an adapter that translates those calls to its API. Adding or swapping a
broker must never require touching strategy logic.
"""
