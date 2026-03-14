"""SQLAlchemy ORM models.

Maps directly to the schema defined in docs/05-database-schema.md.
All tables are created/managed by Alembic migrations.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ============================================================
# 1. traders — Known Trader Profiles
# ============================================================
class Trader(Base):
    __tablename__ = "traders"

    wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(100))
    profile_image: Mapped[str | None] = mapped_column(Text)
    x_username: Mapped[str | None] = mapped_column(String(50))

    # Computed scores (updated by analysis engine)
    composite_score: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0, server_default="0"
    )
    best_pnl_all_time: Mapped[float] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    best_pnl_monthly: Mapped[float] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    best_pnl_weekly: Mapped[float] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    best_pnl_daily: Mapped[float] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    win_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    total_trades: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Tracking
    is_watched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    watch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    specializations: Mapped[dict | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )

    # Metadata
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    # Relationships
    leaderboard_snapshots: Mapped[list[LeaderboardSnapshot]] = relationship(
        back_populates="trader"
    )
    positions: Mapped[list[TraderPosition]] = relationship(back_populates="trader")

    __table_args__ = (
        Index("idx_traders_composite_score", composite_score.desc()),
        Index("idx_traders_is_watched", is_watched, postgresql_where=(is_watched == True)),  # noqa: E712
        Index("idx_traders_last_seen", last_seen_at),
    )


# ============================================================
# 2. leaderboard_snapshots — Historical Leaderboard Data
# ============================================================
class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trader_wallet: Mapped[str] = mapped_column(
        String(42), ForeignKey("traders.wallet"), nullable=False
    )

    # Leaderboard dimensions
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # DAY, WEEK, MONTH, ALL
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # OVERALL, POLITICS, etc.

    # Ranking data
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    # Snapshot time
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    # Relationships
    trader: Mapped[Trader] = relationship(back_populates="leaderboard_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "trader_wallet", "period", "category", "captured_at",
            name="uq_leaderboard_snapshot",
        ),
        Index("idx_lb_trader_period", trader_wallet, period, category),
        Index("idx_lb_captured_at", captured_at),
        Index("idx_lb_pnl", pnl.desc()),
    )


# ============================================================
# 3. markets — Polymarket Market Metadata
# ============================================================
class Market(Base):
    __tablename__ = "markets"

    condition_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(50))

    # Market structure (JSONB)
    outcomes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    token_ids: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Current state
    current_prices: Mapped[dict | None] = mapped_column(JSONB)
    volume: Mapped[float] = mapped_column(Numeric(18, 2), default=0, server_default="0")
    liquidity: Mapped[float] = mapped_column(Numeric(18, 2), default=0, server_default="0")

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    settled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    winning_outcome: Mapped[str | None] = mapped_column(String(50))

    # Dates
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    __table_args__ = (
        Index("idx_markets_category", category),
        Index("idx_markets_active", active, postgresql_where=(active == True)),  # noqa: E712
        Index("idx_markets_liquidity", liquidity.desc()),
    )


# ============================================================
# 4. trader_positions — Current & Historical Positions
# ============================================================
class TraderPosition(Base):
    __tablename__ = "trader_positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trader_wallet: Mapped[str] = mapped_column(
        String(42), ForeignKey("traders.wallet"), nullable=False
    )
    condition_id: Mapped[str] = mapped_column(
        String(66), nullable=False  # No FK — positions may reference markets not yet synced
    )
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)

    # Position data
    size: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    avg_entry_price: Mapped[float | None] = mapped_column(Numeric(10, 6))
    current_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(18, 2))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN", server_default="'OPEN'"
    )

    # Tracking
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    trader: Mapped[Trader] = relationship(back_populates="positions")
    snapshots: Mapped[list[PositionSnapshot]] = relationship(back_populates="position")

    __table_args__ = (
        UniqueConstraint("trader_wallet", "token_id", "status", name="uq_trader_position"),
        Index("idx_positions_trader", trader_wallet),
        Index("idx_positions_status", status),
        Index("idx_positions_market", condition_id),
        Index("idx_positions_detected", first_detected_at),
    )


# ============================================================
# 5. position_snapshots — Position History for Analysis
# ============================================================
class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trader_positions.id"), nullable=False
    )
    trader_wallet: Mapped[str] = mapped_column(String(42), nullable=False)
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)

    size: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    current_price: Mapped[float | None] = mapped_column(Numeric(10, 6))
    current_value: Mapped[float | None] = mapped_column(Numeric(18, 2))

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    # Relationships
    position: Mapped[TraderPosition] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("idx_pos_snap_position", position_id),
        Index("idx_pos_snap_time", captured_at),
    )


# ============================================================
# 6. copy_signals — Detected Trading Signals
# ============================================================
class CopySignal(Base):
    __tablename__ = "copy_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trader_wallet: Mapped[str] = mapped_column(
        String(42), ForeignKey("traders.wallet"), nullable=False
    )

    # Signal details
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    condition_id: Mapped[str] = mapped_column(String(66), nullable=False)
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)

    # Change details
    previous_size: Mapped[float] = mapped_column(Numeric(18, 6), default=0, server_default="0")
    new_size: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    size_change: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    # Market context
    market_price: Mapped[float | None] = mapped_column(Numeric(10, 6))
    market_liquidity: Mapped[float | None] = mapped_column(Numeric(18, 2))

    # Processing
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="'PENDING'"
    )
    reject_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    orders: Mapped[list[CopyOrder]] = relationship(back_populates="signal")

    __table_args__ = (
        Index("idx_signals_status", status),
        Index("idx_signals_trader", trader_wallet),
        Index("idx_signals_created", created_at),
    )


# ============================================================
# 7. copy_orders — Executed Copy Orders
# ============================================================
class CopyOrder(Base):
    __tablename__ = "copy_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("copy_signals.id"), nullable=False
    )

    # Order details
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    requested_size: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    requested_price: Mapped[float | None] = mapped_column(Numeric(10, 6))

    # Execution results
    polymarket_order_id: Mapped[str | None] = mapped_column(String(100))
    fill_price: Mapped[float | None] = mapped_column(Numeric(10, 6))
    fill_size: Mapped[float | None] = mapped_column(Numeric(18, 6))
    slippage_bps: Mapped[float | None] = mapped_column(Numeric(8, 2))
    usdc_spent: Mapped[float | None] = mapped_column(Numeric(18, 2))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="'PENDING'"
    )
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    signal: Mapped[CopySignal] = relationship(back_populates="orders")

    __table_args__ = (
        Index("idx_orders_signal", signal_id),
        Index("idx_orders_status", status),
        Index("idx_orders_created", created_at),
    )


# ============================================================
# 8. portfolio_snapshots — Our Portfolio Over Time
# ============================================================
class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    total_value_usdc: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    total_invested: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    total_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    num_open_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    num_traders_copied: Mapped[int] = mapped_column(Integer, nullable=False)

    max_single_exposure: Mapped[float | None] = mapped_column(Numeric(18, 2))
    portfolio_diversity: Mapped[float | None] = mapped_column(Numeric(5, 4))

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )

    __table_args__ = (Index("idx_portfolio_time", captured_at),)


# ============================================================
# 9. app_config — Runtime Configuration
# ============================================================
class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )


# ============================================================
# 10. trade_history — Historical Trade Activities (Phase 7)
# ============================================================
class TradeHistory(Base):
    """Historical trade activity record from Polymarket Data API.

    Crawled via /activity endpoint. Uses UPSERT (ON CONFLICT DO NOTHING)
    to support idempotent re-crawling without data loss.
    """

    __tablename__ = "trade_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trader_wallet: Mapped[str] = mapped_column(String(42), nullable=False)

    # Trade details
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    condition_id: Mapped[str | None] = mapped_column(String(100))
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False)  # TRADE, SPLIT, MERGE, REDEEM
    side: Mapped[str | None] = mapped_column(String(10))  # MAKER, TAKER, BUY, SELL
    size: Mapped[float | None] = mapped_column(Numeric(20, 6))
    usdc_size: Mapped[float | None] = mapped_column(Numeric(20, 6))
    price: Mapped[float | None] = mapped_column(Numeric(10, 6))
    asset: Mapped[str | None] = mapped_column(Text)  # Subgraph asset IDs can be very long
    outcome_index: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(50))
    transaction_hash: Mapped[str | None] = mapped_column(String(200))  # Subgraph: txHash_orderHash

    # Denormalized market info (from API response, for quick display)
    market_title: Mapped[str | None] = mapped_column(Text)
    market_slug: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        UniqueConstraint(
            "trader_wallet", "transaction_hash", "asset",
            name="uq_trade_history_tx",
        ),
        Index("idx_th_trader", trader_wallet),
        Index("idx_th_timestamp", timestamp),
        Index("idx_th_trader_time", trader_wallet, timestamp),
        Index("idx_th_condition", condition_id),
        Index("idx_th_type", trade_type),
    )


# ============================================================
# 11. crawl_progress — Track crawler state per trader (Phase 7)
# ============================================================
class CrawlProgress(Base):
    """Tracks how far we've crawled each trader's history.

    Enables incremental crawling: on re-run, uses newest_timestamp
    to resume from where we left off with timestamp_gte queries.
    """

    __tablename__ = "crawl_progress"

    trader_wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    activities_crawled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    oldest_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    newest_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default="'PENDING'"
    )  # PENDING, RUNNING, COMPLETE, ERROR
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
