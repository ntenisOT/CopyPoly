"""Analysis & Strategy package.

Core components:
- scorer            — Composite scoring engine (5-dimension weighted score)
- conflict_resolver — NET SIGNAL approach for opposing positions
- position_sizer    — Score-based position sizing with risk limits
- watchlist         — Automatic watchlist management from scores
"""

from copypoly.analysis.conflict_resolver import ConflictResult, resolve_conflicts
from copypoly.analysis.position_sizer import PositionSizeResult, compute_position_size
from copypoly.analysis.scorer import TraderScore, score_all_traders
from copypoly.analysis.watchlist import update_watchlist

__all__ = [
    "ConflictResult",
    "PositionSizeResult",
    "TraderScore",
    "compute_position_size",
    "resolve_conflicts",
    "score_all_traders",
    "update_watchlist",
]
