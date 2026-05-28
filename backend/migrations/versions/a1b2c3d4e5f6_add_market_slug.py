"""add market_slug to copied_trades

Revision ID: a1b2c3d4e5f6
Revises: 25239ccd3168
Create Date: 2026-05-28 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '25239ccd3168'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('copied_trades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('market_slug', sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('copied_trades', schema=None) as batch_op:
        batch_op.drop_column('market_slug')
