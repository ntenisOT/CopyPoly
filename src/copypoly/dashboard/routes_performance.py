"""Performance & chart data endpoints.

Provides equity curve, trade markers, and drawdown data
for the TradingView Lightweight Charts frontend.

When real data is insufficient (< 30 data points), generates
realistic simulated data to demonstrate the dashboard.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from copypoly.db.models import CopyOrder, PortfolioSnapshot
from copypoly.db.session import async_session_factory

router = APIRouter(prefix="/api", tags=["performance"])


def _generate_simulated_equity(
    capital: float = 5000.0,
    days: int = 90,
    seed: int = 42,
) -> dict:
    """Generate realistic simulated equity curve + trades.

    Uses a mean-reverting random walk with momentum and volatility clustering
    to produce a plausible equity curve for a copy-trading strategy.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    equity_data = []
    trades = []
    value = capital
    peak = capital
    drawdown_data = []

    # Volatility regime
    base_vol = 0.008  # 0.8% daily vol
    vol = base_vol
    momentum = 0.0

    for day in range(days + 1):
        date = start + timedelta(days=day)
        ts = date.strftime("%Y-%m-%d")

        # Volatility clustering
        vol = 0.85 * vol + 0.15 * base_vol + rng.gauss(0, 0.001)
        vol = max(0.002, min(0.025, vol))

        # Mean-reverting drift with slight positive bias (good traders)
        drift = 0.0008 + momentum * 0.3  # slight upward drift
        shock = rng.gauss(drift, vol)
        momentum = 0.6 * momentum + 0.4 * shock

        value *= (1 + shock)
        value = max(value * 0.7, value)  # circuit breaker

        peak = max(peak, value)
        dd = (value - peak) / peak

        equity_data.append({
            "time": ts,
            "value": round(value, 2),
        })
        drawdown_data.append({
            "time": ts,
            "value": round(dd * 100, 2),
        })

        # Generate trades on ~40% of days
        if rng.random() < 0.40 and day > 0:
            is_buy = rng.random() < 0.55
            pnl = rng.gauss(8, 35) if is_buy else rng.gauss(-5, 30)
            trade_size = round(rng.uniform(20, 200), 2)

            # Create a deterministic market name from day
            markets = [
                "Presidential Election 2028", "Fed Rate Decision",
                "Bitcoin > $150K", "ETH > $10K", "World Cup Winner",
                "SpaceX Mars Landing", "Apple $300", "Gold > $3500",
                "UK PM Next", "Euro 2028 Winner", "S&P 500 > 7000",
                "OpenAI IPO 2026", "Tesla > $500", "US GDP > 3%",
                "Climate Bill Passes", "NBA Champion 2026",
            ]
            market = markets[day % len(markets)]

            trades.append({
                "time": ts,
                "position": "belowBar" if is_buy else "aboveBar",
                "color": "#10b981" if pnl > 0 else "#ef4444",
                "shape": "arrowUp" if is_buy else "arrowDown",
                "text": f"{'BUY' if is_buy else 'SELL'} ${trade_size}",
                "size": trade_size,
                "pnl": round(pnl, 2),
                "market": market,
            })

    # Summary stats
    total_pnl = value - capital
    roi = (total_pnl / capital) * 100
    winning = [t for t in trades if t["pnl"] > 0]
    win_rate = len(winning) / len(trades) if trades else 0
    max_dd = min(d["value"] for d in drawdown_data)

    return {
        "equity": equity_data,
        "drawdown": drawdown_data,
        "trades": trades,
        "summary": {
            "starting_capital": capital,
            "current_value": round(value, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi, 2),
            "total_trades": len(trades),
            "win_rate": round(win_rate, 3),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_estimate": round(roi / (abs(max_dd) + 1), 2),
            "days": days,
            "is_simulated": True,
        },
    }


@router.get("/performance")
async def get_performance(days: int = 90, capital: float = 5000.0) -> dict:
    """Get equity curve, trade markers, and performance summary.

    Returns real data from portfolio_snapshots + copy_orders when available.
    Falls back to realistic simulated data for demonstration.
    """
    async with async_session_factory() as session:
        # Check if we have real portfolio snapshots
        snapshot_count = (await session.execute(
            select(func.count()).select_from(PortfolioSnapshot)
        )).scalar() or 0

        order_count = (await session.execute(
            select(func.count()).select_from(CopyOrder)
        )).scalar() or 0

    # If we have enough real data, use it
    if snapshot_count >= 30:
        return await _get_real_performance(days)

    # Otherwise, generate simulated data
    return _generate_simulated_equity(capital=capital, days=days)


async def _get_real_performance(days: int) -> dict:
    """Build performance data from real portfolio snapshots."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with async_session_factory() as session:
        snapshots = (await session.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.captured_at >= cutoff)
            .order_by(PortfolioSnapshot.captured_at)
        )).scalars().all()

        orders = (await session.execute(
            select(CopyOrder)
            .where(CopyOrder.executed_at >= cutoff)
            .order_by(CopyOrder.executed_at)
        )).scalars().all()

    equity = [
        {"time": s.captured_at.strftime("%Y-%m-%d"), "value": float(s.total_value_usdc)}
        for s in snapshots
    ]

    peak = 0
    drawdown = []
    for pt in equity:
        peak = max(peak, pt["value"])
        dd = ((pt["value"] - peak) / peak * 100) if peak > 0 else 0
        drawdown.append({"time": pt["time"], "value": round(dd, 2)})

    trades = [
        {
            "time": o.executed_at.strftime("%Y-%m-%d") if o.executed_at else None,
            "position": "belowBar" if o.side == "BUY" else "aboveBar",
            "color": "#10b981" if o.side == "BUY" else "#ef4444",
            "shape": "arrowUp" if o.side == "BUY" else "arrowDown",
            "text": f"{o.side} ${float(o.fill_size or 0):.0f}",
            "size": float(o.fill_size or 0),
            "pnl": 0,
            "market": o.token_id[:16],
        }
        for o in orders
        if o.executed_at
    ]

    if equity:
        total_pnl = equity[-1]["value"] - equity[0]["value"]
        roi = (total_pnl / equity[0]["value"]) * 100 if equity[0]["value"] else 0
    else:
        total_pnl = roi = 0

    return {
        "equity": equity,
        "drawdown": drawdown,
        "trades": trades,
        "summary": {
            "starting_capital": equity[0]["value"] if equity else 0,
            "current_value": equity[-1]["value"] if equity else 0,
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi, 2),
            "total_trades": len(trades),
            "win_rate": 0,
            "max_drawdown_pct": min((d["value"] for d in drawdown), default=0),
            "days": days,
            "is_simulated": False,
        },
    }
