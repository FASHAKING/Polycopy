"""add proportional sizing mode

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-28 12:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'sizing_mode',
                sa.String(length=16),
                nullable=False,
                server_default='multiplier',
            )
        )
    with op.batch_alter_table('follows', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('sizing_mode_override', sa.String(length=16), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('follows', schema=None) as batch_op:
        batch_op.drop_column('sizing_mode_override')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('sizing_mode')
