"""Order Executor — Paper and Live trading execution.

Supports two modes:
  PAPER — Simulates trades, logs to DB, tracks hypothetical PnL
  LIVE  — Submits real orders to Polymarket via CLOB API

Always starts in PAPER mode for safety.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update as sql_update

from copypoly.db.models import CopyOrder, CopySignal
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of an order execution (paper or live)."""

    order_id: int
    signal_id: int
    status: str  # FILLED, FAILED, PARTIAL
    fill_price: float
    fill_size: float
    usdc_spent: float
    slippage_bps: float
    is_paper: bool
    error: str | None = None


class BaseExecutor(ABC):
    """Base class for order execution."""

    @abstractmethod
    async def execute_order(
        self,
        signal: CopySignal,
        usdc_amount: float,
        side: str,
        price: float | None = None,
    ) -> ExecutionResult:
        """Execute a single order.

        Args:
            signal: The copy signal that triggered this order.
            usdc_amount: Amount in USDC to trade.
            side: "BUY" or "SELL".
            price: Limit price (None for market order).

        Returns:
            ExecutionResult with fill details.
        """
        ...


class PaperExecutor(BaseExecutor):
    """Paper trading executor — simulates trades without real money.

    Assumes instant fill at current market price with configurable slippage.
    """

    def __init__(self, default_slippage_bps: int = 50) -> None:
        self.default_slippage_bps = default_slippage_bps

    async def execute_order(
        self,
        signal: CopySignal,
        usdc_amount: float,
        side: str,
        price: float | None = None,
    ) -> ExecutionResult:
        """Simulate a paper trade.

        Fill price = market price ± slippage.
        """
        market_price = float(signal.market_price or 0.50)
        slippage_mult = self.default_slippage_bps / 10000

        if side == "BUY":
            fill_price = min(market_price * (1 + slippage_mult), 0.99)
        else:
            fill_price = max(market_price * (1 - slippage_mult), 0.01)

        fill_size = usdc_amount / fill_price if fill_price > 0 else 0
        slippage_cost = usdc_amount * slippage_mult

        # Calculate actual slippage in bps
        actual_slippage = (
            abs(fill_price - market_price) / market_price * 10000
            if market_price > 0 else 0
        )

        now = datetime.now(timezone.utc)

        # Create order record
        async with async_session_factory() as session:
            order = CopyOrder(
                signal_id=signal.id,
                order_type="MARKET",
                token_id=signal.token_id,
                side=side,
                requested_size=fill_size,
                requested_price=price or market_price,
                polymarket_order_id=f"PAPER-{signal.id}-{int(now.timestamp())}",
                fill_price=fill_price,
                fill_size=fill_size,
                slippage_bps=round(actual_slippage, 2),
                usdc_spent=usdc_amount,
                status="FILLED",
                is_paper=True,
                submitted_at=now,
                executed_at=now,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)

        log.info(
            "paper_trade_executed",
            signal_id=signal.id,
            order_id=order.id,
            side=side,
            usdc=round(usdc_amount, 2),
            fill_price=round(fill_price, 4),
            fill_size=round(fill_size, 2),
            slippage_bps=round(actual_slippage, 1),
            market=signal.condition_id[:20],
        )

        return ExecutionResult(
            order_id=order.id,
            signal_id=signal.id,
            status="FILLED",
            fill_price=fill_price,
            fill_size=fill_size,
            usdc_spent=usdc_amount,
            slippage_bps=round(actual_slippage, 2),
            is_paper=True,
        )


class LiveExecutor(BaseExecutor):
    """Live trading executor — submits real orders to Polymarket CLOB.

    ⚠️ DANGER: Uses real money. Must be explicitly enabled.
    Requires CLOB API credentials and wallet configuration.
    """

    def __init__(self) -> None:
        # Will be initialized with CLOB client when ready
        self._enabled = False

    async def execute_order(
        self,
        signal: CopySignal,
        usdc_amount: float,
        side: str,
        price: float | None = None,
    ) -> ExecutionResult:
        """Execute a live order on Polymarket.

        Currently raises NotImplementedError — will be implemented
        when CLOB integration is complete and tested.
        """
        if not self._enabled:
            raise RuntimeError(
                "Live trading is disabled. Enable with extreme caution. "
                "Use PaperExecutor for testing."
            )

        # TODO: Implement CLOB order submission
        # 1. Build order params (token_id, side, size, price)
        # 2. Sign with wallet private key
        # 3. Submit to CLOB API
        # 4. Poll for fill confirmation
        # 5. Record result
        raise NotImplementedError("Live trading not yet implemented")


class CopyEngine:
    """Main copy trading engine — orchestrates signal → execution flow.

    Wraps the signal detector and executor to provide a single
    entry point for processing position changes.
    """

    def __init__(self, executor: BaseExecutor | None = None) -> None:
        from copypoly.engine.signal_detector import SignalDetector

        self.signal_detector = SignalDetector()
        self.executor = executor or PaperExecutor()

    async def handle_new_position(
        self,
        wallet: str,
        position: Any,
        api_data: dict[str, Any],
    ) -> ExecutionResult | None:
        """Handle a newly detected trader position.

        Full pipeline: detect signal → evaluate → execute.
        """
        from copypoly.engine.signal_detector import evaluate_signal

        signal = await self.signal_detector.process_new_position(
            wallet, position, api_data
        )
        if not signal:
            return None

        evaluation = await evaluate_signal(signal)
        if not evaluation["approved"]:
            log.info(
                "signal_rejected",
                signal_id=signal.id,
                reason=evaluation.get("reject_reason"),
            )
            return None

        return await self.executor.execute_order(
            signal=signal,
            usdc_amount=evaluation["usdc_amount"],
            side="BUY",
        )

    async def handle_closed_position(
        self,
        wallet: str,
        position: Any,
    ) -> ExecutionResult | None:
        """Handle a closed trader position — sell our copy."""
        signal = await self.signal_detector.process_closed_position(
            wallet, position
        )
        if not signal:
            return None

        # For closes, we always sell if we hold the position
        # Skip the full evaluation — just execute
        async with async_session_factory() as session:
            # Check if we have a matching copy order
            from sqlalchemy import select
            result = await session.execute(
                select(CopyOrder)
                .join(CopySignal)
                .where(
                    CopySignal.condition_id == signal.condition_id,
                    CopyOrder.status == "FILLED",
                    CopyOrder.side == "BUY",
                )
                .limit(1)
            )
            our_position = result.scalar()

        if our_position:
            return await self.executor.execute_order(
                signal=signal,
                usdc_amount=float(our_position.usdc_spent or 0),
                side="SELL",
            )

        return None
