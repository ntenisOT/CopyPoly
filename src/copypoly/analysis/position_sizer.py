"""Position Sizer — Determines how much capital to allocate per copy signal.

Uses the trader's composite score and risk parameters to determine
position sizing. Higher-scored traders get larger allocations.

Sizing formula:
    base_allocation = total_capital × max_position_pct
    trader_allocation = base_allocation × composite_score
    final_size = trader_allocation × confidence_multiplier
"""

from __future__ import annotations

from dataclasses import dataclass

from copypoly.analysis.conflict_resolver import ConflictResult
from copypoly.analysis.scorer import TraderScore
from copypoly.logging import get_logger

log = get_logger(__name__)


@dataclass
class PositionSizeResult:
    """Computed position size for a copy signal."""

    trader_wallet: str
    condition_id: str
    outcome: str
    usdc_amount: float    # How much USDC to commit
    share_size: float     # Approximate shares at current price
    allocation_pct: float  # What % of portfolio this uses

    # Inputs used
    trader_score: float
    confidence: float
    current_price: float
    total_capital: float


# Default risk parameters (overrideable via app_config)
DEFAULT_RISK_PARAMS = {
    "max_position_pct": 0.10,       # Max 10% of capital per trade
    "max_single_trader_pct": 0.25,  # Max 25% of capital per trader
    "max_single_market_pct": 0.20,  # Max 20% of capital per market
    "min_position_usdc": 5.0,       # Minimum $5 position
    "max_position_usdc": 500.0,     # Maximum $500 per position
    "score_power": 1.5,             # Score exponent (> 1 favors high scorers)
}


def compute_position_size(
    trader: TraderScore,
    conflict: ConflictResult,
    current_price: float,
    total_capital: float,
    risk_params: dict | None = None,
) -> PositionSizeResult:
    """Compute the optimal position size for a copy signal.

    Args:
        trader: Scored trader that generated the signal.
        conflict: Conflict resolution result for this market.
        current_price: Current market price for the outcome (0.0-1.0).
        total_capital: Total available capital in USDC.
        risk_params: Risk parameters (defaults used if None).

    Returns:
        PositionSizeResult with computed sizing.
    """
    params = risk_params or dict(DEFAULT_RISK_PARAMS)

    # Base allocation scaled by score
    score = min(max(trader.composite_score, 0), 1)
    score_multiplier = score ** params["score_power"]

    base_usdc = total_capital * params["max_position_pct"]
    confidence_mult = conflict.confidence  # 0.0 → 1.0

    usdc_amount = base_usdc * score_multiplier * confidence_mult

    # Apply min/max bounds
    usdc_amount = max(usdc_amount, params["min_position_usdc"])
    usdc_amount = min(usdc_amount, params["max_position_usdc"])
    usdc_amount = min(usdc_amount, total_capital * params["max_single_trader_pct"])

    # Don't trade if below minimum after adjustments
    if usdc_amount < params["min_position_usdc"]:
        usdc_amount = 0.0

    # Compute approximate shares
    share_price = max(current_price, 0.01)  # Avoid division by zero
    share_size = usdc_amount / share_price

    allocation_pct = usdc_amount / total_capital if total_capital > 0 else 0

    result = PositionSizeResult(
        trader_wallet=trader.wallet,
        condition_id=conflict.condition_id,
        outcome=conflict.outcome,
        usdc_amount=round(usdc_amount, 2),
        share_size=round(share_size, 4),
        allocation_pct=round(allocation_pct, 4),
        trader_score=round(score, 4),
        confidence=round(confidence_mult, 4),
        current_price=round(current_price, 6),
        total_capital=total_capital,
    )

    log.debug(
        "position_sized",
        wallet=trader.wallet[:12],
        usdc=result.usdc_amount,
        shares=result.share_size,
        allocation_pct=f"{allocation_pct:.1%}",
        score=round(score, 3),
        confidence=round(confidence_mult, 3),
    )

    return result
