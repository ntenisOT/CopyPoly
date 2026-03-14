"""Conflict Resolver — Handles opposing positions across watched traders.

When multiple watched traders hold positions on the SAME market:
- If they all agree (same outcome) → Strong signal, increase confidence
- If they disagree (opposite outcomes) → Conflict, reduce or skip

Resolution strategy: NET SIGNAL approach
  1. Sum all watched traders' positions per outcome, weighted by their composite score
  2. Follow the majority (score-weighted)
  3. Reduce position size proportionally to conflict severity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copypoly.db.models import Trader, TraderPosition
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)


@dataclass
class TraderSignal:
    """A single trader's position in a market."""

    wallet: str
    username: str | None
    composite_score: float
    outcome: str  # "Yes" or "No"
    size: float
    weighted_size: float = 0.0  # size × composite_score


@dataclass
class ConflictResult:
    """Result of conflict resolution for a single market."""

    condition_id: str
    outcome: str  # Resolved direction ("Yes" or "No")
    confidence: float  # 0.0 → 1.0 (1.0 = full agreement, 0.0 = dead split)
    net_signal_strength: float  # Magnitude of the net weighted position
    should_trade: bool  # Whether the signal is strong enough to act on

    # Details
    agree_count: int = 0  # Number of traders agreeing with majority
    disagree_count: int = 0  # Number of traders holding the opposite
    total_traders: int = 0
    signals: list[TraderSignal] = field(default_factory=list)
    reject_reason: str | None = None

    @property
    def conflict_severity(self) -> float:
        """How severe the conflict is (0=none, 1=dead split)."""
        return 1.0 - self.confidence


async def resolve_conflicts(
    condition_id: str,
    min_confidence: float = 0.3,
) -> ConflictResult:
    """Resolve conflicting positions for a specific market.

    Args:
        condition_id: The market's condition ID.
        min_confidence: Minimum confidence to allow trading (0.0-1.0).

    Returns:
        ConflictResult with resolved direction, confidence, and trade decision.
    """
    async with async_session_factory() as session:
        # Get all open positions from watched traders in this market
        result = await session.execute(
            select(TraderPosition, Trader)
            .join(Trader, TraderPosition.trader_wallet == Trader.wallet)
            .where(
                TraderPosition.condition_id == condition_id,
                TraderPosition.status == "OPEN",
                Trader.is_watched == True,  # noqa: E712
            )
        )
        rows = result.all()

    if not rows:
        return ConflictResult(
            condition_id=condition_id,
            outcome="",
            confidence=0.0,
            net_signal_strength=0.0,
            should_trade=False,
            reject_reason="No watched traders hold positions in this market",
        )

    # Build signals
    signals: list[TraderSignal] = []
    for position, trader in rows:
        score = float(trader.composite_score or 0)
        sig = TraderSignal(
            wallet=trader.wallet,
            username=trader.username,
            composite_score=score,
            outcome=position.outcome,
            size=float(position.size),
            weighted_size=float(position.size) * score,
        )
        signals.append(sig)

    # Group by outcome
    outcome_weights: dict[str, float] = {}
    outcome_counts: dict[str, int] = {}

    for sig in signals:
        outcome_weights[sig.outcome] = outcome_weights.get(sig.outcome, 0) + sig.weighted_size
        outcome_counts[sig.outcome] = outcome_counts.get(sig.outcome, 0) + 1

    # Find the majority outcome (score-weighted)
    majority_outcome = max(outcome_weights, key=outcome_weights.get)  # type: ignore
    majority_weight = outcome_weights[majority_outcome]
    total_weight = sum(outcome_weights.values())

    # Confidence = how much of the total weight agrees
    confidence = majority_weight / total_weight if total_weight > 0 else 0.0

    # Count agree/disagree
    agree_count = outcome_counts.get(majority_outcome, 0)
    disagree_count = len(signals) - agree_count

    should_trade = confidence >= min_confidence

    result = ConflictResult(
        condition_id=condition_id,
        outcome=majority_outcome,
        confidence=round(confidence, 4),
        net_signal_strength=round(majority_weight - (total_weight - majority_weight), 4),
        should_trade=should_trade,
        agree_count=agree_count,
        disagree_count=disagree_count,
        total_traders=len(signals),
        signals=signals,
    )

    if not should_trade:
        result.reject_reason = (
            f"Confidence {confidence:.1%} below threshold {min_confidence:.1%} "
            f"({agree_count} agree, {disagree_count} disagree)"
        )

    log.info(
        "conflict_resolved",
        condition_id=condition_id[:20],
        outcome=majority_outcome,
        confidence=confidence,
        agree=agree_count,
        disagree=disagree_count,
        should_trade=should_trade,
    )

    return result


async def resolve_all_conflicts() -> dict[str, ConflictResult]:
    """Resolve conflicts across ALL markets where watched traders have positions.

    Returns:
        Dict mapping condition_id → ConflictResult.
    """
    # Find all markets with positions from watched traders
    async with async_session_factory() as session:
        result = await session.execute(
            select(TraderPosition.condition_id)
            .distinct()
            .join(Trader, TraderPosition.trader_wallet == Trader.wallet)
            .where(
                TraderPosition.status == "OPEN",
                Trader.is_watched == True,  # noqa: E712
            )
        )
        condition_ids = [row[0] for row in result.fetchall()]

    results: dict[str, ConflictResult] = {}
    conflicts_found = 0

    for cid in condition_ids:
        cr = await resolve_conflicts(cid)
        results[cid] = cr
        if cr.disagree_count > 0:
            conflicts_found += 1

    log.info(
        "all_conflicts_resolved",
        markets=len(condition_ids),
        conflicts=conflicts_found,
    )

    return results
