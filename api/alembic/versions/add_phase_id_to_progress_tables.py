"""add phase_id to progress tables

Revision ID: add_phase_id_progress
Revises: merge_heads_20260203
Create Date: 2026-02-03

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_phase_id_progress"
down_revision = "merge_heads_20260203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("step_progress") as batch_op:
        batch_op.add_column(sa.Column("phase_id", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE step_progress
            SET phase_id = NULLIF(
                regexp_replace(split_part(topic_id, '-', 1), 'phase', ''),
                ''
            )::int
            """
        )
    )

    with op.batch_alter_table("step_progress") as batch_op:
        batch_op.alter_column("phase_id", nullable=False)
        batch_op.create_index(
            "ix_step_progress_user_phase",
            ["user_id", "phase_id"],
            unique=False,
        )

    with op.batch_alter_table("question_attempts") as batch_op:
        batch_op.add_column(sa.Column("phase_id", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE question_attempts
            SET phase_id = NULLIF(
                regexp_replace(split_part(topic_id, '-', 1), 'phase', ''),
                ''
            )::int
            """
        )
    )

    with op.batch_alter_table("question_attempts") as batch_op:
        batch_op.alter_column("phase_id", nullable=False)
        batch_op.create_index(
            "ix_question_attempts_user_phase",
            ["user_id", "phase_id"],
            unique=False,
        )

    op.create_index(
        "ix_submissions_user_phase_validated",
        "submissions",
        ["user_id", "phase_id"],
        unique=False,
        postgresql_where=sa.text("is_validated"),
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_user_phase_validated", table_name="submissions")

    with op.batch_alter_table("question_attempts") as batch_op:
        batch_op.drop_index("ix_question_attempts_user_phase")
        batch_op.drop_column("phase_id")

    with op.batch_alter_table("step_progress") as batch_op:
        batch_op.drop_index("ix_step_progress_user_phase")
        batch_op.drop_column("phase_id")
