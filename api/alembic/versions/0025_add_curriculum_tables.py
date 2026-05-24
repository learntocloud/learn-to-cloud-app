"""add curriculum tables

Why this change: Phase B of the curriculum domain model rollout (#463).
Adds DB tables for phases/topics/steps/learning_objectives/requirements
so a later deploy-time sync step can populate them from YAML. App keeps
reading from YAML at runtime in this phase; no FKs from user state to
these tables yet.

Schema effect: Creates 5 new tables, all keyed by UUID with soft-delete
(``deleted_at``), partial unique indexes scoped to active rows, and
``ON DELETE RESTRICT`` foreign keys to enforce the integrity rules
agreed in #461 Q4.

Rollback notes: Pure additive; downgrade drops the tables. No user
state references these yet so downgrade is safe.

Revision ID: 0025_add_curriculum_tables
Create Date: 2026-05-24 17:40:34.560211
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0025_add_curriculum_tables"
down_revision = "0024_db_cleanup_tier1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phases",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name="pk_phases"),
    )
    op.create_index(
        "uq_phases_slug_active",
        "phases",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "topics",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_id", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name="pk_topics"),
        sa.ForeignKeyConstraint(
            ["phase_uuid"],
            ["phases.uuid"],
            name="fk_topics_phase_uuid",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_topics_phase_slug_active",
        "topics",
        ["phase_uuid", "slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "steps",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_id", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column(
            "extra_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name="pk_steps"),
        sa.ForeignKeyConstraint(
            ["topic_uuid"],
            ["topics.uuid"],
            name="fk_steps_topic_uuid",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_steps_topic_order_active",
        "steps",
        ["topic_uuid", "order"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "learning_objectives",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name="pk_learning_objectives"),
        sa.ForeignKeyConstraint(
            ["topic_uuid"],
            ["topics.uuid"],
            name="fk_learning_objectives_topic_uuid",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_learning_objectives_topic_order_active",
        "learning_objectives",
        ["topic_uuid", "order"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "requirements",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("submission_type", sa.Text(), nullable=False),
        sa.Column(
            "type_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name="pk_requirements"),
        sa.ForeignKeyConstraint(
            ["phase_uuid"],
            ["phases.uuid"],
            name="fk_requirements_phase_uuid",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_requirements_phase_id_active",
        "requirements",
        ["phase_uuid", "id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Requirement IDs are globally unique because user-state tables
    # currently store the bare string ID (e.g., "github-profile"), so
    # the same id cannot legitimately exist in two phases without
    # ambiguating Phase D's UUID backfill.
    op.create_index(
        "uq_requirements_id_active",
        "requirements",
        ["id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("requirements")
    op.drop_table("learning_objectives")
    op.drop_table("steps")
    op.drop_table("topics")
    op.drop_table("phases")
