"""Add base_amount and quote_amount raw integer columns to trade_history.

These columns store the exact subgraph integer values (scaled 1e6)
for lossless PnL calculations from DB data.

Revision ID: 003_add_raw_amounts
Revises: a99d9d52b67b
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "003_add_raw_amounts"
down_revision = "a99d9d52b67b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trade_history", sa.Column("base_amount", sa.BigInteger, nullable=True))
    op.add_column("trade_history", sa.Column("quote_amount", sa.BigInteger, nullable=True))


def downgrade() -> None:
    op.drop_column("trade_history", "quote_amount")
    op.drop_column("trade_history", "base_amount")
