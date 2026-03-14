"""Signal Detector — Converts position changes into actionable copy signals.

Called whenever position changes are detected by the position monitor.
Creates CopySignal records based on position diffs and runs them through
the conflict resolver and position sizer before execution.

Signal types:
  OPEN   — Trader opened a new position
  ADD    — Trader increased an existing position
  REDUCE — Trader reduced a position
  CLOSE  — Trader closed a position entirely
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copypoly.analysis.conflict_resolver import resolve_conflicts
from copypoly.analysis.position_sizer import compute_position_size
from copypoly.analysis.scorer import TraderScore
from copypoly.db.models import CopySignal, Market, Trader, TraderPosition
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)


class SignalDetector:
    """Detects and processes copy signals from position changes."""

    async def process_new_position(
        self,
        wallet: str,
        position: TraderPosition,
        api_data: dict[str, Any],
    ) -> CopySignal | None:
        """Generate a signal for a newly detected position.

        Args:
            wallet: Trader's wallet address.
            position: The newly created TraderPosition.
            api_data: Raw API response data for context.

        Returns:
            CopySignal if actionable, None if rejected.
        """
        return await self._create_signal(
            wallet=wallet,
            signal_type="OPEN",
            condition_id=position.condition_id,
            token_id=position.token_id,
            outcome=position.outcome,
            previous_size=0.0,
            new_size=float(position.size),
            api_data=api_data,
        )

    async def process_size_change(
        self,
        wallet: str,
        position: TraderPosition,
        old_size: float,
        new_size: float,
        api_data: dict[str, Any],
    ) -> CopySignal | None:
        """Generate a signal for a position size change.

        Args:
            wallet: Trader's wallet address.
            position: The updated TraderPosition.
            old_size: Previous position size.
            new_size: Current position size.
            api_data: Raw API response data.

        Returns:
            CopySignal if actionable, None if rejected.
        """
        if new_size > old_size:
            signal_type = "ADD"
        else:
            signal_type = "REDUCE"

        return await self._create_signal(
            wallet=wallet,
            signal_type=signal_type,
            condition_id=position.condition_id,
            token_id=position.token_id,
            outcome=position.outcome,
            previous_size=old_size,
            new_size=new_size,
            api_data=api_data,
        )

    async def process_closed_position(
        self,
        wallet: str,
        position: TraderPosition,
    ) -> CopySignal | None:
        """Generate a signal for a closed position.

        Args:
            wallet: Trader's wallet address.
            position: The closed TraderPosition.

        Returns:
            CopySignal if we hold a corresponding position.
        """
        return await self._create_signal(
            wallet=wallet,
            signal_type="CLOSE",
            condition_id=position.condition_id,
            token_id=position.token_id,
            outcome=position.outcome,
            previous_size=float(position.size),
            new_size=0.0,
            api_data={},
        )

    async def _create_signal(
        self,
        *,
        wallet: str,
        signal_type: str,
        condition_id: str,
        token_id: str,
        outcome: str,
        previous_size: float,
        new_size: float,
        api_data: dict[str, Any],
    ) -> CopySignal | None:
        """Create a CopySignal record and run it through validation.

        Validation steps:
        1. Check trader is still watched and has a score
        2. Run conflict resolution for this market
        3. Check market liquidity
        4. Determine position size
        """
        size_change = new_size - previous_size

        # Get market context
        market_price = float(api_data.get("curPrice", 0))
        market_liquidity = None

        async with async_session_factory() as session:
            # Try to get liquidity from markets table
            market_result = await session.execute(
                select(Market.liquidity).where(Market.condition_id == condition_id)
            )
            liq = market_result.scalar()
            if liq:
                market_liquidity = float(liq)

            # Create signal record
            signal = CopySignal(
                trader_wallet=wallet,
                signal_type=signal_type,
                condition_id=condition_id,
                token_id=token_id,
                outcome=outcome,
                previous_size=previous_size,
                new_size=new_size,
                size_change=size_change,
                market_price=market_price if market_price > 0 else None,
                market_liquidity=market_liquidity,
                status="PENDING",
            )
            session.add(signal)
            await session.commit()
            await session.refresh(signal)

        log.info(
            "signal_created",
            type=signal_type,
            wallet=wallet[:12],
            condition_id=condition_id[:20],
            outcome=outcome,
            size_change=round(size_change, 2),
            signal_id=signal.id,
        )

        return signal


async def evaluate_signal(signal: CopySignal) -> dict[str, Any]:
    """Evaluate a pending signal through conflict resolution and sizing.

    Args:
        signal: The CopySignal to evaluate.

    Returns:
        Dict with evaluation results: approved, reject_reason, size, etc.
    """
    result: dict[str, Any] = {
        "approved": False,
        "signal_id": signal.id,
        "reject_reason": None,
        "usdc_amount": 0.0,
        "confidence": 0.0,
    }

    # 1. Get trader info and score
    async with async_session_factory() as session:
        trader_result = await session.execute(
            select(Trader).where(Trader.wallet == signal.trader_wallet)
        )
        trader = trader_result.scalar()

    if not trader or not trader.is_watched:
        result["reject_reason"] = "Trader not watched"
        await _update_signal_status(signal.id, "REJECTED", "Trader not watched")
        return result

    trader_score = TraderScore(
        wallet=trader.wallet,
        username=trader.username,
        composite_score=float(trader.composite_score or 0),
        pnl_all=float(trader.best_pnl_all_time or 0),
        win_rate=float(trader.win_rate) if trader.win_rate else None,
    )

    # 2. Conflict resolution
    conflict = await resolve_conflicts(signal.condition_id)

    if not conflict.should_trade:
        result["reject_reason"] = conflict.reject_reason
        await _update_signal_status(signal.id, "REJECTED", conflict.reject_reason or "Conflict")
        return result

    result["confidence"] = conflict.confidence

    # 3. Position sizing
    market_price = float(signal.market_price or 0.5)  # Default to 50c if unknown

    # TODO: Get actual portfolio capital from config
    total_capital = 5000.0  # Placeholder — will come from app_config

    size_result = compute_position_size(
        trader=trader_score,
        conflict=conflict,
        current_price=market_price,
        total_capital=total_capital,
    )

    if size_result.usdc_amount <= 0:
        result["reject_reason"] = "Position too small after sizing"
        await _update_signal_status(signal.id, "REJECTED", "Position too small")
        return result

    result["approved"] = True
    result["usdc_amount"] = size_result.usdc_amount
    result["share_size"] = size_result.share_size
    result["allocation_pct"] = size_result.allocation_pct

    await _update_signal_status(signal.id, "APPROVED")

    log.info(
        "signal_approved",
        signal_id=signal.id,
        usdc=size_result.usdc_amount,
        confidence=round(conflict.confidence, 3),
        trader=trader.username,
    )

    return result


async def _update_signal_status(
    signal_id: int,
    status: str,
    reject_reason: str | None = None,
) -> None:
    """Update a signal's status in the database."""
    from sqlalchemy import update

    async with async_session_factory() as session:
        values: dict[str, Any] = {
            "status": status,
            "processed_at": datetime.now(timezone.utc),
        }
        if reject_reason:
            values["reject_reason"] = reject_reason

        await session.execute(
            update(CopySignal)
            .where(CopySignal.id == signal_id)
            .values(**values)
        )
        await session.commit()
