"""Backtester — Simulate copy-trading against historical trade data.

Fetches real historical trades from the Polymarket Data API
and replays them to estimate what copy-trading returns would have been.

Key simulation parameters:
- detection_delay_seconds: How long after a trade we detect it (realistic: 30-60s)
- slippage_bps: Expected slippage in basis points (realistic: 50-200bps)
- capture_rate: What fraction of the trader's edge we capture (0.1 - 0.5)
- capital: Our starting capital in USDC
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from copypoly.api.data import DataAPIClient
from copypoly.logging import get_logger

log = get_logger(__name__)


@dataclass
class BacktestTrade:
    """A single trade in the backtest simulation."""

    timestamp: datetime
    trader_wallet: str
    trader_name: str
    condition_id: str
    market_title: str
    outcome: str
    side: str  # BUY or SELL
    size: float
    price: float

    # Our simulated copy
    our_entry_price: float = 0.0  # After slippage
    our_size: float = 0.0  # Position size we take
    our_usdc_spent: float = 0.0
    slippage_applied: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtest result."""

    trader_wallet: str
    trader_name: str
    capital: float
    detection_delay_seconds: int
    slippage_bps: int

    # Results
    total_trades: int = 0
    trades_copied: int = 0
    trades_skipped: int = 0
    total_pnl: float = 0.0
    total_invested: float = 0.0
    total_slippage_cost: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0

    # Time range
    first_trade_at: datetime | None = None
    last_trade_at: datetime | None = None
    days_span: float = 0.0

    # Computed metrics
    roi_pct: float = 0.0
    daily_roi_pct: float = 0.0
    win_rate: float = 0.0
    avg_pnl_per_trade: float = 0.0

    # Individual trades for analysis
    trades: list[BacktestTrade] = field(default_factory=list)

    # Per-market breakdown
    market_pnl: dict[str, float] = field(default_factory=dict)

    def compute_metrics(self) -> None:
        """Calculate derived metrics from raw results."""
        if self.capital > 0:
            self.roi_pct = (self.total_pnl / self.capital) * 100
        if self.days_span > 0:
            self.daily_roi_pct = self.roi_pct / self.days_span
        if self.trades_copied > 0:
            self.win_rate = self.win_count / self.trades_copied
            self.avg_pnl_per_trade = self.total_pnl / self.trades_copied


async def backtest_trader(
    wallet: str,
    *,
    capital: float = 5000.0,
    max_position_pct: float = 0.10,
    detection_delay_seconds: int = 30,
    slippage_bps: int = 100,
    max_trades: int = 2000,
) -> BacktestResult:
    """Run a backtest simulation for a single trader.

    Fetches all historical trades and simulates copy-trading them.

    Args:
        wallet: Trader's proxy wallet address.
        capital: Starting capital in USDC.
        max_position_pct: Max % of capital per trade.
        detection_delay_seconds: Simulated detection delay.
        slippage_bps: Slippage in basis points.
        max_trades: Maximum trades to fetch.

    Returns:
        BacktestResult with full simulation output.
    """
    client = DataAPIClient()
    try:
        # Fetch trader profile
        profile = await client.get_profile(wallet)
        trader_name = profile.get("userName", wallet[:12])

        # Fetch all historical trades
        all_trades = await _fetch_all_trades(client, wallet, max_trades)

        if not all_trades:
            log.warning("no_trades_for_backtest", wallet=wallet[:12])
            return BacktestResult(
                trader_wallet=wallet,
                trader_name=trader_name,
                capital=capital,
                detection_delay_seconds=detection_delay_seconds,
                slippage_bps=slippage_bps,
            )

        # Also fetch closed positions for realized PnL data
        closed = await _fetch_closed_positions(client, wallet)

    finally:
        await client.close()

    log.info(
        "backtest_data_loaded",
        trader=trader_name,
        trades=len(all_trades),
        closed_positions=len(closed),
    )

    # Build market outcome map from closed positions
    market_outcomes: dict[str, dict] = {}
    for cp in closed:
        cid = cp.get("conditionId", "")
        if cid:
            market_outcomes[cid] = {
                "realized_pnl": float(cp.get("realizedPnl", 0)),
                "cur_price": float(cp.get("curPrice", 0)),
                "avg_price": float(cp.get("avgPrice", 0)),
            }

    # Sort trades chronologically (oldest first)
    all_trades.sort(key=lambda t: t.get("timestamp", 0))

    # Simulate
    result = BacktestResult(
        trader_wallet=wallet,
        trader_name=trader_name,
        capital=capital,
        detection_delay_seconds=detection_delay_seconds,
        slippage_bps=slippage_bps,
    )

    remaining_capital = capital
    positions: dict[str, dict] = {}  # condition_id -> our position
    slippage_mult = slippage_bps / 10000

    for raw_trade in all_trades:
        ts = raw_trade.get("timestamp", 0)
        side = raw_trade.get("side", "").upper()
        size = float(raw_trade.get("size", 0))
        price = float(raw_trade.get("price", 0))
        cid = raw_trade.get("conditionId", "")
        outcome = raw_trade.get("outcome", "?")
        title = raw_trade.get("title", "?")

        if not side or not cid or price <= 0:
            result.trades_skipped += 1
            continue

        result.total_trades += 1
        trade_dt = datetime.fromtimestamp(ts) if ts > 0 else None

        if result.first_trade_at is None and trade_dt:
            result.first_trade_at = trade_dt
        if trade_dt:
            result.last_trade_at = trade_dt

        # Simulate our copy
        max_usdc = remaining_capital * max_position_pct
        if max_usdc < 5:  # Min $5 trade
            result.trades_skipped += 1
            continue

        if side == "BUY":
            # We buy with slippage (worse price)
            our_price = min(price * (1 + slippage_mult), 0.99)
            our_usdc = min(max_usdc, remaining_capital * 0.5)  # Don't go all-in
            our_size = our_usdc / our_price if our_price > 0 else 0
            slippage_cost = our_usdc * slippage_mult

            bt = BacktestTrade(
                timestamp=trade_dt or datetime.min,
                trader_wallet=wallet,
                trader_name=trader_name,
                condition_id=cid,
                market_title=str(title)[:60],
                outcome=outcome,
                side="BUY",
                size=size,
                price=price,
                our_entry_price=our_price,
                our_size=our_size,
                our_usdc_spent=our_usdc,
                slippage_applied=slippage_cost,
            )

            # Track position
            if cid not in positions:
                positions[cid] = {
                    "size": 0, "total_cost": 0, "outcome": outcome,
                    "title": str(title)[:60],
                }
            positions[cid]["size"] += our_size
            positions[cid]["total_cost"] += our_usdc
            remaining_capital -= our_usdc

            result.total_invested += our_usdc
            result.total_slippage_cost += slippage_cost
            result.trades_copied += 1
            result.trades.append(bt)

        elif side == "SELL":
            # If we have a position, sell it
            if cid in positions and positions[cid]["size"] > 0:
                pos = positions[cid]
                # Sell at worse price (slippage down)
                our_sell_price = max(price * (1 - slippage_mult), 0.01)
                sell_value = pos["size"] * our_sell_price
                trade_pnl = sell_value - pos["total_cost"]

                remaining_capital += sell_value
                result.total_pnl += trade_pnl

                if cid not in result.market_pnl:
                    result.market_pnl[cid] = 0
                result.market_pnl[cid] += trade_pnl

                if trade_pnl > 0:
                    result.win_count += 1
                    result.best_trade_pnl = max(result.best_trade_pnl, trade_pnl)
                else:
                    result.loss_count += 1
                    result.worst_trade_pnl = min(result.worst_trade_pnl, trade_pnl)

                result.trades_copied += 1
                del positions[cid]

    # Mark-to-market remaining positions using closed position data
    for cid, pos in positions.items():
        if cid in market_outcomes:
            final_price = market_outcomes[cid]["cur_price"]
            if final_price > 0:
                final_value = pos["size"] * final_price
                unrealized = final_value - pos["total_cost"]
                result.total_pnl += unrealized

    # Compute time span
    if result.first_trade_at and result.last_trade_at:
        delta = result.last_trade_at - result.first_trade_at
        result.days_span = max(delta.total_seconds() / 86400, 1)

    result.compute_metrics()

    log.info(
        "backtest_complete",
        trader=trader_name,
        total_pnl=round(result.total_pnl, 2),
        roi_pct=round(result.roi_pct, 2),
        daily_roi=round(result.daily_roi_pct, 2),
        win_rate=round(result.win_rate, 3),
        trades=result.trades_copied,
        days=round(result.days_span, 1),
    )

    return result


async def backtest_top_traders(
    n_traders: int = 5,
    **kwargs: Any,
) -> list[BacktestResult]:
    """Backtest the top N traders from the leaderboard.

    Args:
        n_traders: Number of top traders to backtest.
        **kwargs: Passed to backtest_trader().

    Returns:
        List of BacktestResult, sorted by ROI.
    """
    client = DataAPIClient()
    try:
        lb = await client.get_leaderboard(period="all", limit=n_traders)
    finally:
        await client.close()

    results = []
    for entry in lb:
        wallet = entry.get("proxyWallet", "")
        if not wallet:
            continue

        result = await backtest_trader(wallet, **kwargs)
        results.append(result)

    results.sort(key=lambda r: r.roi_pct, reverse=True)
    return results


async def _fetch_all_trades(
    client: DataAPIClient,
    wallet: str,
    max_trades: int = 2000,
) -> list[dict]:
    """Paginate through all available trades for a wallet."""
    all_trades: list[dict] = []
    offset = 0
    page_size = 100

    while len(all_trades) < max_trades:
        try:
            batch = await client.get_trades(wallet, limit=page_size, offset=offset)
        except Exception:
            break

        if not isinstance(batch, list) or not batch:
            break

        all_trades.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return all_trades[:max_trades]


async def _fetch_closed_positions(
    client: DataAPIClient,
    wallet: str,
) -> list[dict]:
    """Fetch all closed positions for a wallet."""
    try:
        result = await client.get_closed_positions(wallet, limit=100)
        return result if isinstance(result, list) else []
    except Exception:
        return []
