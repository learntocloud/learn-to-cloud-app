"""add step_progress.step_uuid (Phase D.1a)

Why this change: Phase D of #461 migrates user state tables to reference
curriculum entities by UUID instead of free-form legacy string IDs. This
is PR D.1a -- the additive, dual-write half. PR D.1b will switch app
reads to ``step_uuid``; PR D.1c will drop the legacy columns and add
``NOT NULL`` + FK.

Schema effect:
- Adds ``step_progress.step_uuid UUID`` (nullable, no FK yet).
- Adds an index on ``step_uuid`` so the future FK lookup is cheap.
- Backfills ``step_uuid`` for existing rows by joining
  ``topics.legacy_id = step_progress.topic_id`` and
  ``steps.legacy_id = step_progress.step_id`` against the active
  (non-soft-deleted) curriculum.
- Deletes rows whose ``(topic_id, step_id)`` no longer maps to any active
  step. These rows were already invisible to users -- the read path in
  ``get_valid_completed_steps`` filters completions against the current
  topic's step IDs, so a stale row never contributed to displayed
  progress. The DELETE makes the eventual ``NOT NULL`` constraint
  achievable without losing user-visible progress.

Production preflight (2026-05-24, prior to this migration):

    step_progress rows                            : 49060
    distinct users                                :  2466
    rows with topic_id matching topics.legacy_id  : 49060
    rows with step lookup match                   : 48942

So this migration soft-cleans up 118 rows that already had no on-screen
effect.

Rollback notes: ``downgrade()`` drops the column and the index. The
deleted stale rows are not restored -- they were already invisible to
users, and reintroducing them would not change any user-visible state.

Revision ID: 0027_step_progress_step_uuid
Create Date: 2026-05-24 19:45:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_step_progress_step_uuid"
down_revision = "0026_add_requirements_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")

    op.add_column(
        "step_progress",
        sa.Column("step_uuid", sa.Uuid(as_uuid=True), nullable=True),
    )

    op.execute(
        """
        UPDATE step_progress sp
        SET step_uuid = s.uuid
        FROM steps s
        JOIN topics t ON s.topic_uuid = t.uuid
        WHERE t.legacy_id = sp.topic_id
          AND s.legacy_id = sp.step_id
          AND s.deleted_at IS NULL
          AND t.deleted_at IS NULL
        """
    )

    op.execute(
        """
        DELETE FROM step_progress
        WHERE step_uuid IS NULL
        """
    )

    # CREATE INDEX CONCURRENTLY requires running outside of a transaction.
    # autocommit_block commits the current tx, runs the index build, then
    # opens a fresh tx for any later statements. ``IF NOT EXISTS`` makes
    # the build idempotent if a previous deploy attempt was killed
    # mid-create (which would otherwise leave an INVALID index behind).
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_step_progress_step_uuid ON step_progress (step_uuid)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_step_progress_step_uuid")
    op.drop_column("step_progress", "step_uuid")
