"""add paper account balance and positions

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 00:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'paper_starting_balance', sa.Float(), nullable=False, server_default='0'
            )
        )
        batch_op.add_column(
            sa.Column('paper_balance', sa.Float(), nullable=False, server_default='0')
        )
        batch_op.add_column(sa.Column('paper_funded_at', sa.DateTime(), nullable=True))

    op.create_table(
        'paper_positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_id', sa.String(length=128), nullable=False),
        sa.Column('condition_id', sa.String(length=128), nullable=False),
        sa.Column('market_question', sa.String(length=512), nullable=True),
        sa.Column('market_slug', sa.String(length=256), nullable=True),
        sa.Column('outcome', sa.String(length=32), nullable=False),
        sa.Column('shares', sa.Float(), nullable=False),
        sa.Column('avg_price', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'token_id', name='uq_paper_user_token'),
    )
    with op.batch_alter_table('paper_positions', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_paper_positions_user_id'), ['user_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_paper_positions_token_id'), ['token_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('paper_positions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_paper_positions_token_id'))
        batch_op.drop_index(batch_op.f('ix_paper_positions_user_id'))
    op.drop_table('paper_positions')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('paper_funded_at')
        batch_op.drop_column('paper_balance')
        batch_op.drop_column('paper_starting_balance')
