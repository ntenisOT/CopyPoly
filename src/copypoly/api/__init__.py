"""Polymarket API clients package.

Three API clients matching Polymarket's API architecture:

- GammaAPIClient — Market discovery and metadata (public)
- DataAPIClient  — Leaderboard, positions, trades (public/mixed)
- ClobAPIClient  — Order book and trade execution (auth for trading)
"""

from copypoly.api.clob import ClobAPIClient
from copypoly.api.data import DataAPIClient
from copypoly.api.gamma import GammaAPIClient

__all__ = [
    "ClobAPIClient",
    "DataAPIClient",
    "GammaAPIClient",
]
