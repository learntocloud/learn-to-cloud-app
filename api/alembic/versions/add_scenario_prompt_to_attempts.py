"""add scenario_prompt to question_attempts

Revision ID: add_scenario_prompt
Revises: b2c3d4e5f6g7
Create Date: 2026-01-25

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_scenario_prompt"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add scenario_prompt column to store the dynamically generated scenario
    # that was shown to the user when they answered. Nullable since existing
    # records won't have this, and fallback scenarios use the base prompt.
    op.add_column(
        "question_attempts",
        sa.Column("scenario_prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("question_attempts", "scenario_prompt")
