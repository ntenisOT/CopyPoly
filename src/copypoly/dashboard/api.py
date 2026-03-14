"""Dashboard REST API — Endpoints for the CopyPoly dashboard.

All endpoints return JSON. The frontend consumes these.

Routes:
    GET  /api/overview          — Portfolio summary + key metrics
    GET  /api/traders           — All watched traders with scores
    GET  /api/traders/{wallet}  — Single trader detail
    GET  /api/positions         — All open positions across watched traders
    GET  /api/signals           — Recent copy signals
    GET  /api/orders            — Recent copy orders (paper + live)
    GET  /api/config            — All app config values
    PUT  /api/config/{key}      — Update a config value
    POST /api/backtest          — Trigger a backtest run
    POST /api/collect           — Trigger leaderboard collection
    POST /api/score             — Trigger scoring + watchlist update
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update

from copypoly.db.models import (
    AppConfig,
    CopyOrder,
    CopySignal,
    LeaderboardSnapshot,
    PortfolioSnapshot,
    Trader,
    TraderPosition,
)
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


# ----------------------------------------------------------------
# Pydantic models for request/response
# ----------------------------------------------------------------
class ConfigUpdate(BaseModel):
    value: Any


class BacktestRequest(BaseModel):
    wallet: str | None = None
    n_traders: int = 5
    capital: float = 5000.0
    slippage_bps: int = 100


# ----------------------------------------------------------------
# Overview
# ----------------------------------------------------------------
@router.get("/overview")
async def get_overview() -> dict:
    """Portfolio overview with key metrics."""
    async with async_session_factory() as session:
        total_traders = (await session.execute(
            select(func.count()).select_from(Trader)
        )).scalar() or 0

        watched_traders = (await session.execute(
            select(func.count()).select_from(Trader).where(Trader.is_watched == True)  # noqa: E712
        )).scalar() or 0

        open_positions = (await session.execute(
            select(func.count()).select_from(TraderPosition).where(
                TraderPosition.status == "OPEN"
            )
        )).scalar() or 0

        total_signals = (await session.execute(
            select(func.count()).select_from(CopySignal)
        )).scalar() or 0

        total_orders = (await session.execute(
            select(func.count()).select_from(CopyOrder)
        )).scalar() or 0

        paper_orders = (await session.execute(
            select(func.count()).select_from(CopyOrder).where(CopyOrder.is_paper == True)  # noqa: E712
        )).scalar() or 0

        # Latest portfolio snapshot
        latest_portfolio = (await session.execute(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.captured_at.desc())
            .limit(1)
        )).scalar()

        # Trading mode from config
        mode_row = (await session.execute(
            select(AppConfig.value).where(AppConfig.key == "trading_mode")
        )).scalar()

    return {
        "total_traders": total_traders,
        "watched_traders": watched_traders,
        "open_positions": open_positions,
        "total_signals": total_signals,
        "total_orders": total_orders,
        "paper_orders": paper_orders,
        "trading_mode": mode_row or "paper",
        "portfolio": {
            "total_value": float(latest_portfolio.total_value_usdc) if latest_portfolio else 0,
            "total_pnl": float(latest_portfolio.total_pnl) if latest_portfolio else 0,
            "unrealized_pnl": float(latest_portfolio.unrealized_pnl) if latest_portfolio else 0,
        } if latest_portfolio else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ----------------------------------------------------------------
# Traders
# ----------------------------------------------------------------
@router.get("/traders")
async def get_traders(watched_only: bool = False) -> list[dict]:
    """Get all traders, optionally filtered to watched only."""
    async with async_session_factory() as session:
        query = select(Trader).order_by(Trader.composite_score.desc())
        if watched_only:
            query = query.where(Trader.is_watched == True)  # noqa: E712

        result = await session.execute(query)
        traders = result.scalars().all()

        trader_list = []
        for t in traders:
            # Count open positions
            pos_count = (await session.execute(
                select(func.count()).select_from(TraderPosition).where(
                    TraderPosition.trader_wallet == t.wallet,
                    TraderPosition.status == "OPEN",
                )
            )).scalar() or 0

            trader_list.append({
                "wallet": t.wallet,
                "username": t.username,
                "profile_image": t.profile_image,
                "composite_score": float(t.composite_score or 0),
                "best_pnl_all_time": float(t.best_pnl_all_time or 0),
                "best_pnl_monthly": float(t.best_pnl_monthly or 0),
                "best_pnl_weekly": float(t.best_pnl_weekly or 0),
                "best_pnl_daily": float(t.best_pnl_daily or 0),
                "win_rate": float(t.win_rate) if t.win_rate else None,
                "total_trades": t.total_trades or 0,
                "is_watched": t.is_watched,
                "open_positions": pos_count,
                "last_seen_at": t.last_seen_at.isoformat() if t.last_seen_at else None,
                "last_scored_at": t.last_scored_at.isoformat() if t.last_scored_at else None,
            })

    return trader_list


@router.get("/traders/{wallet}")
async def get_trader_detail(wallet: str) -> dict:
    """Get detailed info for a single trader including positions."""
    async with async_session_factory() as session:
        trader = (await session.execute(
            select(Trader).where(Trader.wallet == wallet)
        )).scalar()

        if not trader:
            raise HTTPException(status_code=404, detail="Trader not found")

        positions = (await session.execute(
            select(TraderPosition).where(
                TraderPosition.trader_wallet == wallet,
                TraderPosition.status == "OPEN",
            ).order_by(TraderPosition.size.desc())
        )).scalars().all()

        # Recent leaderboard snapshots
        snapshots = (await session.execute(
            select(LeaderboardSnapshot).where(
                LeaderboardSnapshot.trader_wallet == wallet
            ).order_by(LeaderboardSnapshot.captured_at.desc()).limit(20)
        )).scalars().all()

    return {
        "wallet": trader.wallet,
        "username": trader.username,
        "composite_score": float(trader.composite_score or 0),
        "is_watched": trader.is_watched,
        "best_pnl_all_time": float(trader.best_pnl_all_time or 0),
        "positions": [
            {
                "condition_id": p.condition_id,
                "token_id": p.token_id,
                "outcome": p.outcome,
                "size": float(p.size),
                "avg_entry_price": float(p.avg_entry_price) if p.avg_entry_price else None,
                "current_value": float(p.current_value) if p.current_value else None,
                "first_detected_at": p.first_detected_at.isoformat() if p.first_detected_at else None,
            }
            for p in positions
        ],
        "snapshots": [
            {
                "period": s.period,
                "rank": s.rank,
                "pnl": float(s.pnl),
                "volume": float(s.volume),
                "captured_at": s.captured_at.isoformat() if s.captured_at else None,
            }
            for s in snapshots
        ],
    }


# ----------------------------------------------------------------
# Positions
# ----------------------------------------------------------------
@router.get("/positions")
async def get_positions(status: str = "OPEN") -> list[dict]:
    """Get positions, optionally filtered by status."""
    async with async_session_factory() as session:
        query = (
            select(TraderPosition, Trader.username)
            .join(Trader, TraderPosition.trader_wallet == Trader.wallet)
            .where(TraderPosition.status == status)
            .order_by(TraderPosition.size.desc())
            .limit(500)
        )
        result = await session.execute(query)
        rows = result.all()

    return [
        {
            "id": pos.id,
            "trader_wallet": pos.trader_wallet,
            "trader_name": username,
            "condition_id": pos.condition_id,
            "token_id": pos.token_id,
            "outcome": pos.outcome,
            "size": float(pos.size),
            "avg_entry_price": float(pos.avg_entry_price) if pos.avg_entry_price else None,
            "current_value": float(pos.current_value) if pos.current_value else None,
            "status": pos.status,
            "first_detected_at": pos.first_detected_at.isoformat() if pos.first_detected_at else None,
        }
        for pos, username in rows
    ]


# ----------------------------------------------------------------
# Signals & Orders
# ----------------------------------------------------------------
@router.get("/signals")
async def get_signals(limit: int = 50) -> list[dict]:
    """Get recent copy signals."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(CopySignal)
            .order_by(CopySignal.created_at.desc())
            .limit(limit)
        )
        signals = result.scalars().all()

    return [
        {
            "id": s.id,
            "trader_wallet": s.trader_wallet,
            "signal_type": s.signal_type,
            "condition_id": s.condition_id,
            "outcome": s.outcome,
            "size_change": float(s.size_change),
            "market_price": float(s.market_price) if s.market_price else None,
            "status": s.status,
            "reject_reason": s.reject_reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]


@router.get("/orders")
async def get_orders(limit: int = 50) -> list[dict]:
    """Get recent copy orders."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(CopyOrder)
            .order_by(CopyOrder.created_at.desc())
            .limit(limit)
        )
        orders = result.scalars().all()

    return [
        {
            "id": o.id,
            "signal_id": o.signal_id,
            "side": o.side,
            "token_id": o.token_id,
            "requested_size": float(o.requested_size),
            "fill_price": float(o.fill_price) if o.fill_price else None,
            "fill_size": float(o.fill_size) if o.fill_size else None,
            "usdc_spent": float(o.usdc_spent) if o.usdc_spent else None,
            "slippage_bps": float(o.slippage_bps) if o.slippage_bps else None,
            "status": o.status,
            "is_paper": o.is_paper,
            "executed_at": o.executed_at.isoformat() if o.executed_at else None,
        }
        for o in orders
    ]


# ----------------------------------------------------------------
# Config
# ----------------------------------------------------------------
@router.get("/config")
async def get_config() -> list[dict]:
    """Get all app configuration values."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AppConfig).order_by(AppConfig.key)
        )
        configs = result.scalars().all()

    return [
        {
            "key": c.key,
            "value": c.value,
            "description": c.description,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in configs
    ]


@router.put("/config/{key}")
async def update_config(key: str, body: ConfigUpdate) -> dict:
    """Update a configuration value."""
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(AppConfig).where(AppConfig.key == key)
        )).scalar()

        if not existing:
            raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")

        await session.execute(
            update(AppConfig)
            .where(AppConfig.key == key)
            .values(
                value=body.value,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    log.info("config_updated", key=key, new_value=str(body.value)[:100])
    return {"key": key, "value": body.value, "status": "updated"}


# ----------------------------------------------------------------
# Actions
# ----------------------------------------------------------------
@router.post("/collect")
async def trigger_collection() -> dict:
    """Trigger a leaderboard collection manually."""
    from copypoly.collectors.leaderboard import collect_leaderboard

    stats = await collect_leaderboard()
    return {"status": "complete", "stats": stats}


@router.post("/score")
async def trigger_scoring() -> dict:
    """Trigger trader scoring and watchlist update."""
    from copypoly.analysis.watchlist import update_watchlist

    stats = await update_watchlist()
    return {"status": "complete", "stats": stats}


@router.post("/backtest")
async def trigger_backtest(body: BacktestRequest) -> dict:
    """Run a backtest and return results."""
    from copypoly.analysis.backtester import backtest_top_traders, backtest_trader

    if body.wallet:
        result = await backtest_trader(
            body.wallet,
            capital=body.capital,
            slippage_bps=body.slippage_bps,
        )
        results = [result]
    else:
        results = await backtest_top_traders(
            n_traders=body.n_traders,
            capital=body.capital,
            slippage_bps=body.slippage_bps,
        )

    return {
        "status": "complete",
        "results": [
            {
                "trader_name": r.trader_name,
                "trader_wallet": r.trader_wallet,
                "total_trades": r.total_trades,
                "trades_copied": r.trades_copied,
                "total_pnl": round(r.total_pnl, 2),
                "roi_pct": round(r.roi_pct, 2),
                "daily_roi_pct": round(r.daily_roi_pct, 3),
                "win_rate": round(r.win_rate, 3),
                "days_span": round(r.days_span, 1),
                "slippage_cost": round(r.total_slippage_cost, 2),
                "first_trade": r.first_trade_at.isoformat() if r.first_trade_at else None,
                "last_trade": r.last_trade_at.isoformat() if r.last_trade_at else None,
            }
            for r in results
        ],
    }
