"""add crawl_runs table and resync_count

Revision ID: a99d9d52b67b
Revises: 002_trade_history
Create Date: 2026-03-15 14:27:48.962442

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a99d9d52b67b'
down_revision: Union[str, None] = '002_trade_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add resync_count to crawl_progress
    op.add_column('crawl_progress',
        sa.Column('resync_count', sa.Integer(), nullable=False, server_default='0')
    )

    # Create crawl_runs table
    op.create_table('crawl_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('total_traders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ok_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warn_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('resync_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_events', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('new_events', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('crawl_runs')
    op.drop_column('crawl_progress', 'resync_count')
