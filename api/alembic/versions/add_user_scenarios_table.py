"""add user_scenarios table

Revision ID: add_user_scenarios
Revises: add_scenario_prompt
Create Date: 2026-01-25

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_user_scenarios"
down_revision = "add_scenario_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_scenarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("question_id", sa.String(length=100), nullable=False),
        sa.Column("scenario_prompt", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_user_scenario"),
    )
    op.create_index(
        "ix_user_scenarios_lookup",
        "user_scenarios",
        ["user_id", "question_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_scenarios_lookup", table_name="user_scenarios")
    op.drop_table("user_scenarios")
