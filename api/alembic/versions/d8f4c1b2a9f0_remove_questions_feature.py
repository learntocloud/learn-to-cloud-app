"""remove questions feature

Revision ID: d8f4c1b2a9f0
Revises: merge_heads_20260203
Create Date: 2026-02-10

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d8f4c1b2a9f0"
down_revision = "merge_heads_20260203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM user_activities WHERE activity_type = 'question_attempt'")

    with op.batch_alter_table("user_phase_progress", schema=None) as batch_op:
        batch_op.drop_column("questions_passed")

    op.drop_table("user_scenarios")
    op.drop_table("question_attempts")

    old_enum = sa.Enum(
        "question_attempt",
        "step_complete",
        "topic_complete",
        "hands_on_validated",
        "phase_complete",
        "certificate_earned",
        name="activity_type",
        native_enum=False,
    )
    new_enum = sa.Enum(
        "step_complete",
        "topic_complete",
        "hands_on_validated",
        "phase_complete",
        "certificate_earned",
        name="activity_type",
        native_enum=False,
    )

    with op.batch_alter_table("user_activities", schema=None) as batch_op:
        batch_op.alter_column(
            "activity_type",
            existing_type=old_enum,
            type_=new_enum,
            nullable=False,
        )


def downgrade() -> None:
    old_enum = sa.Enum(
        "step_complete",
        "topic_complete",
        "hands_on_validated",
        "phase_complete",
        "certificate_earned",
        name="activity_type",
        native_enum=False,
    )
    new_enum = sa.Enum(
        "question_attempt",
        "step_complete",
        "topic_complete",
        "hands_on_validated",
        "phase_complete",
        "certificate_earned",
        name="activity_type",
        native_enum=False,
    )

    with op.batch_alter_table("user_activities", schema=None) as batch_op:
        batch_op.alter_column(
            "activity_type",
            existing_type=old_enum,
            type_=new_enum,
            nullable=False,
        )

    op.create_table(
        "question_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("topic_id", sa.String(length=100), nullable=False),
        sa.Column("question_id", sa.String(length=100), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("scenario_prompt", sa.Text(), nullable=True),
        sa.Column("is_passed", sa.Boolean(), nullable=False),
        sa.Column("llm_feedback", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("question_attempts", schema=None) as batch_op:
        batch_op.create_index(
            "ix_question_attempts_user_question",
            ["user_id", "question_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_question_attempts_user_topic",
            ["user_id", "topic_id"],
            unique=False,
        )

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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_user_scenario"),
    )
    op.create_index(
        "ix_user_scenarios_lookup",
        "user_scenarios",
        ["user_id", "question_id"],
    )

    with op.batch_alter_table("user_phase_progress", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "questions_passed",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
