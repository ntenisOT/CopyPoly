"""Initial schema — all 9 tables.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-03-14

This migration creates the complete CopyPoly database schema.
It is designed to be fully idempotent — `alembic upgrade head`
always brings the DB to the correct state from scratch.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- 1. traders ----
    op.create_table(
        "traders",
        sa.Column("wallet", sa.String(42), primary_key=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("profile_image", sa.Text(), nullable=True),
        sa.Column("x_username", sa.String(50), nullable=True),
        sa.Column("composite_score", sa.Numeric(10, 4), server_default="0"),
        sa.Column("best_pnl_all_time", sa.Numeric(18, 2), server_default="0"),
        sa.Column("best_pnl_monthly", sa.Numeric(18, 2), server_default="0"),
        sa.Column("best_pnl_weekly", sa.Numeric(18, 2), server_default="0"),
        sa.Column("best_pnl_daily", sa.Numeric(18, 2), server_default="0"),
        sa.Column("win_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("total_trades", sa.Integer(), server_default="0"),
        sa.Column("is_watched", sa.Boolean(), server_default="false"),
        sa.Column("watch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("specializations", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_traders_composite_score", "traders", [sa.text("composite_score DESC")])
    op.create_index(
        "idx_traders_is_watched", "traders", ["is_watched"],
        postgresql_where=sa.text("is_watched = true"),
    )
    op.create_index("idx_traders_last_seen", "traders", ["last_seen_at"])

    # ---- 2. leaderboard_snapshots ----
    op.create_table(
        "leaderboard_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("trader_wallet", sa.String(42), sa.ForeignKey("traders.wallet"), nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("pnl", sa.Numeric(18, 2), nullable=False),
        sa.Column("volume", sa.Numeric(18, 2), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "trader_wallet", "period", "category", "captured_at",
            name="uq_leaderboard_snapshot",
        ),
    )
    op.create_index("idx_lb_trader_period", "leaderboard_snapshots", ["trader_wallet", "period", "category"])
    op.create_index("idx_lb_captured_at", "leaderboard_snapshots", ["captured_at"])
    op.create_index("idx_lb_pnl", "leaderboard_snapshots", [sa.text("pnl DESC")])

    # ---- 3. markets ----
    op.create_table(
        "markets",
        sa.Column("condition_id", sa.String(66), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(200), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("outcomes", postgresql.JSONB(), nullable=False),
        sa.Column("token_ids", postgresql.JSONB(), nullable=False),
        sa.Column("current_prices", postgresql.JSONB(), nullable=True),
        sa.Column("volume", sa.Numeric(18, 2), server_default="0"),
        sa.Column("liquidity", sa.Numeric(18, 2), server_default="0"),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column("settled", sa.Boolean(), server_default="false"),
        sa.Column("winning_outcome", sa.String(50), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_markets_category", "markets", ["category"])
    op.create_index(
        "idx_markets_active", "markets", ["active"],
        postgresql_where=sa.text("active = true"),
    )
    op.create_index("idx_markets_liquidity", "markets", [sa.text("liquidity DESC")])

    # ---- 4. trader_positions ----
    op.create_table(
        "trader_positions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("trader_wallet", sa.String(42), sa.ForeignKey("traders.wallet"), nullable=False),
        sa.Column("condition_id", sa.String(66), nullable=False),  # No FK — positions may reference markets not yet synced
        sa.Column("token_id", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("size", sa.Numeric(18, 6), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(10, 6), nullable=True),
        sa.Column("current_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'OPEN'"),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("trader_wallet", "token_id", "status", name="uq_trader_position"),
    )
    op.create_index("idx_positions_trader", "trader_positions", ["trader_wallet"])
    op.create_index("idx_positions_status", "trader_positions", ["status"])
    op.create_index("idx_positions_market", "trader_positions", ["condition_id"])
    op.create_index("idx_positions_detected", "trader_positions", ["first_detected_at"])

    # ---- 5. position_snapshots ----
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("position_id", sa.BigInteger(), sa.ForeignKey("trader_positions.id"), nullable=False),
        sa.Column("trader_wallet", sa.String(42), nullable=False),
        sa.Column("token_id", sa.String(100), nullable=False),
        sa.Column("size", sa.Numeric(18, 6), nullable=False),
        sa.Column("current_price", sa.Numeric(10, 6), nullable=True),
        sa.Column("current_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_pos_snap_position", "position_snapshots", ["position_id"])
    op.create_index("idx_pos_snap_time", "position_snapshots", ["captured_at"])

    # ---- 6. copy_signals ----
    op.create_table(
        "copy_signals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("trader_wallet", sa.String(42), sa.ForeignKey("traders.wallet"), nullable=False),
        sa.Column("signal_type", sa.String(20), nullable=False),
        sa.Column("condition_id", sa.String(66), nullable=False),
        sa.Column("token_id", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("previous_size", sa.Numeric(18, 6), server_default="0"),
        sa.Column("new_size", sa.Numeric(18, 6), nullable=False),
        sa.Column("size_change", sa.Numeric(18, 6), nullable=False),
        sa.Column("market_price", sa.Numeric(10, 6), nullable=True),
        sa.Column("market_liquidity", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'PENDING'"),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_signals_status", "copy_signals", ["status"])
    op.create_index("idx_signals_trader", "copy_signals", ["trader_wallet"])
    op.create_index("idx_signals_created", "copy_signals", ["created_at"])

    # ---- 7. copy_orders ----
    op.create_table(
        "copy_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("signal_id", sa.BigInteger(), sa.ForeignKey("copy_signals.id"), nullable=False),
        sa.Column("order_type", sa.String(10), nullable=False),
        sa.Column("token_id", sa.String(100), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("requested_size", sa.Numeric(18, 6), nullable=False),
        sa.Column("requested_price", sa.Numeric(10, 6), nullable=True),
        sa.Column("polymarket_order_id", sa.String(100), nullable=True),
        sa.Column("fill_price", sa.Numeric(10, 6), nullable=True),
        sa.Column("fill_size", sa.Numeric(18, 6), nullable=True),
        sa.Column("slippage_bps", sa.Numeric(8, 2), nullable=True),
        sa.Column("usdc_spent", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'PENDING'"),
        sa.Column("is_paper", sa.Boolean(), server_default="true"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_orders_signal", "copy_orders", ["signal_id"])
    op.create_index("idx_orders_status", "copy_orders", ["status"])
    op.create_index("idx_orders_created", "copy_orders", ["created_at"])

    # ---- 8. portfolio_snapshots ----
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("total_value_usdc", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_invested", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_pnl", sa.Numeric(18, 2), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(18, 2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 2), nullable=False),
        sa.Column("num_open_positions", sa.Integer(), nullable=False),
        sa.Column("num_traders_copied", sa.Integer(), nullable=False),
        sa.Column("max_single_exposure", sa.Numeric(18, 2), nullable=True),
        sa.Column("portfolio_diversity", sa.Numeric(5, 4), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_portfolio_time", "portfolio_snapshots", ["captured_at"])

    # ---- 9. app_config ----
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ---- Seed app_config with defaults ----
    op.execute("""
        INSERT INTO app_config (key, value, description) VALUES
            ('min_trader_win_rate', '0.55', 'Minimum win rate for trader eligibility'),
            ('min_trader_trades', '50', 'Minimum total trades for eligibility'),
            ('min_trader_pnl', '0', 'Minimum PnL for eligibility'),
            ('active_recency_days', '7', 'Trader must have been active within N days'),
            ('max_concentration_pct', '0.60', 'Max pct of PnL from a single market'),
            ('min_market_liquidity_usdc', '5000', 'Minimum market liquidity to trade'),
            ('scorer_weights', '{"pnl": 0.3, "win_rate": 0.25, "consistency": 0.2, "volume": 0.15, "roi": 0.1}', 'Weights for composite trader scoring'),
            ('max_traders_to_watch', '10', 'Maximum number of traders to actively copy'),
            ('position_sizing', '{"cash_reserve_pct": 0.20, "max_per_trader_allocation": 0.25, "max_per_market_allocation": 0.15, "max_single_position_usdc": 200, "max_market_impact_pct": 0.02, "min_consensus_threshold": 0.30, "min_trade_size_usdc": 5.0}', 'Position sizing configuration'),
            ('max_total_exposure_usdc', '1000', 'Maximum total portfolio exposure'),
            ('slippage_tolerance_bps', '200', 'Max slippage in basis points (2 pct)'),
            ('daily_loss_limit_usdc', '100', 'Stop copying if daily loss exceeds this'),
            ('trading_mode', '"paper"', 'Trading mode: paper or live'),
            ('leaderboard_update_interval_minutes', '5', 'How often to fetch leaderboard data'),
            ('position_check_interval_seconds', '30', 'How often to check watched trader positions'),
            ('market_sync_interval_minutes', '15', 'How often to refresh market metadata')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_table("portfolio_snapshots")
    op.drop_table("copy_orders")
    op.drop_table("copy_signals")
    op.drop_table("position_snapshots")
    op.drop_table("trader_positions")
    op.drop_table("markets")
    op.drop_table("leaderboard_snapshots")
    op.drop_table("traders")
