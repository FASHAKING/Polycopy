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
    # Idempotent: a DB first built by create_all may already have some of these
    # objects (new tables get created, but existing tables don't get new columns),
    # so each step only runs when the target is actually missing.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    user_cols = {c["name"] for c in insp.get_columns("users")}

    if "paper_starting_balance" not in user_cols:
        op.add_column(
            "users",
            sa.Column("paper_starting_balance", sa.Float(), nullable=False, server_default="0"),
        )
    if "paper_balance" not in user_cols:
        op.add_column(
            "users", sa.Column("paper_balance", sa.Float(), nullable=False, server_default="0")
        )
    if "paper_funded_at" not in user_cols:
        op.add_column("users", sa.Column("paper_funded_at", sa.DateTime(), nullable=True))

    if not insp.has_table("paper_positions"):
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

    existing_idx = {i["name"] for i in insp.get_indexes("paper_positions")} if insp.has_table(
        "paper_positions"
    ) else set()
    if "ix_paper_positions_user_id" not in existing_idx:
        op.create_index(
            op.f('ix_paper_positions_user_id'), 'paper_positions', ['user_id'], unique=False
        )
    if "ix_paper_positions_token_id" not in existing_idx:
        op.create_index(
            op.f('ix_paper_positions_token_id'), 'paper_positions', ['token_id'], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("paper_positions"):
        op.drop_table('paper_positions')

    user_cols = {c["name"] for c in insp.get_columns("users")}
    with op.batch_alter_table('users', schema=None) as batch_op:
        if "paper_funded_at" in user_cols:
            batch_op.drop_column('paper_funded_at')
        if "paper_balance" in user_cols:
            batch_op.drop_column('paper_balance')
        if "paper_starting_balance" in user_cols:
            batch_op.drop_column('paper_starting_balance')
