"""add account snapshots for the P&L chart

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-28 13:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'account_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account', sa.String(length=8), nullable=False),
        sa.Column('portfolio_value', sa.Float(), nullable=False),
        sa.Column('pnl', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('account_snapshots', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_account_snapshots_user_id'), ['user_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_account_snapshots_created_at'), ['created_at'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('account_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_account_snapshots_created_at'))
        batch_op.drop_index(batch_op.f('ix_account_snapshots_user_id'))
    op.drop_table('account_snapshots')
