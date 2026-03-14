"""Add trade_history and crawl_progress tables for Phase 7.

Revision ID: 002_trade_history
Revises: 001_initial_schema
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "002_trade_history"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # trade_history — historical trade activities from Polymarket Data API
    op.create_table(
        "trade_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trader_wallet", sa.String(42), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("condition_id", sa.String(100), nullable=True),
        sa.Column("trade_type", sa.String(20), nullable=False),
        sa.Column("side", sa.String(4), nullable=True),
        sa.Column("size", sa.Numeric(20, 6), nullable=True),
        sa.Column("usdc_size", sa.Numeric(20, 6), nullable=True),
        sa.Column("price", sa.Numeric(10, 6), nullable=True),
        sa.Column("asset", sa.String(100), nullable=True),
        sa.Column("outcome_index", sa.Integer, nullable=True),
        sa.Column("outcome", sa.String(50), nullable=True),
        sa.Column("transaction_hash", sa.String(66), nullable=True),
        sa.Column("market_title", sa.Text, nullable=True),
        sa.Column("market_slug", sa.String(200), nullable=True),
        sa.UniqueConstraint(
            "trader_wallet", "transaction_hash", "asset",
            name="uq_trade_history_tx",
        ),
    )

    op.create_index("idx_th_trader", "trade_history", ["trader_wallet"])
    op.create_index("idx_th_timestamp", "trade_history", ["timestamp"])
    op.create_index("idx_th_trader_time", "trade_history", ["trader_wallet", "timestamp"])
    op.create_index("idx_th_condition", "trade_history", ["condition_id"])
    op.create_index("idx_th_type", "trade_history", ["trade_type"])

    # crawl_progress — tracks crawler state per trader
    op.create_table(
        "crawl_progress",
        sa.Column("trader_wallet", sa.String(42), primary_key=True),
        sa.Column("activities_crawled", sa.Integer, server_default="0"),
        sa.Column("oldest_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("newest_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="'PENDING'"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("crawl_progress")
    op.drop_table("trade_history")
