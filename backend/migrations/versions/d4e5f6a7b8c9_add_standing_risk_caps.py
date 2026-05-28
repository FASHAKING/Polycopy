"""add standing-risk caps (exposure, position count, price filter)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-28 13:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'max_open_exposure_usd', sa.Float(), nullable=False, server_default='0'
            )
        )
        batch_op.add_column(
            sa.Column(
                'max_open_positions', sa.BigInteger(), nullable=False, server_default='0'
            )
        )
        batch_op.add_column(
            sa.Column('min_price', sa.Float(), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('max_price', sa.Float(), nullable=False, server_default='1')
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('max_price')
        batch_op.drop_column('min_price')
        batch_op.drop_column('max_open_positions')
        batch_op.drop_column('max_open_exposure_usd')
