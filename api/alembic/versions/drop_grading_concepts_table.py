"""drop grading_concepts table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-18 14:00:00.000000

This migration removes the grading_concepts table since grading data
is now embedded directly in the content JSON files (expected_concepts
field in each question).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop grading_concepts table - data is now in content JSON files."""
    with op.batch_alter_table("grading_concepts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_grading_concepts_question_id"))
    op.drop_table("grading_concepts")


def downgrade() -> None:
    """Recreate grading_concepts table (data will need to be re-seeded)."""
    op.create_table(
        "grading_concepts",
        sa.Column("question_id", sa.String(length=100), nullable=False),
        sa.Column("expected_concepts", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("question_id"),
    )
    with op.batch_alter_table("grading_concepts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_grading_concepts_question_id"),
            ["question_id"],
            unique=False,
        )
