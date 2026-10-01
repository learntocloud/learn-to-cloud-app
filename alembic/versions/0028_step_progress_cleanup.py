"""step_progress UUID FK cleanup (Phase D.1bc)

Why this change: closes Phase D.1 of #461 / #465. With ``step_uuid``
backfilled and dual-written in production (PR #477), this migration
makes ``steps.uuid`` the only curriculum reference and drops the legacy
``topic_id`` / ``step_id`` / ``phase_id`` / ``step_order`` columns.

Schema effect:

- ``step_progress.step_uuid`` becomes ``NOT NULL``.
- Adds ``fk_step_progress_step_uuid`` referencing ``steps(uuid)`` with
  ``ON DELETE RESTRICT`` to prevent hard-deleting a step that has
  recorded user progress.
- Replaces the legacy unique constraint
  ``uq_user_topic_step (user_id, topic_id, step_id)`` with
  ``uq_step_progress_user_step (user_id, step_uuid)`` -- the new
  invariant we actually want.
- Drops the legacy indexes ``ix_step_progress_user_topic`` and
  ``ix_step_progress_user_phase`` since they cover columns that are
  about to be dropped.
- Drops ``topic_id`` / ``step_id`` / ``phase_id`` / ``step_order``.

Production preflight (2026-05-24, after Phase D.1a deploy):

    alembic head                   : 0027_step_progress_step_uuid
    total rows                     : 48943
    step_uuid NULL                 : 0
    distinct step_uuid             : 272
    rows where step_uuid resolves  : 48943

So the FK + NOT NULL are safe -- every row points to an active step.

Rollback notes: ``downgrade()`` re-adds the legacy columns + indexes +
constraint as nullable. It does NOT re-derive ``topic_id`` / ``step_id``
/ ``phase_id`` / ``step_order`` from ``step_uuid``; restoring those
values is left to a manual backfill if a rollback ever happens, since
this PR's whole point is to make the legacy columns redundant.

Revision ID: 0028_step_progress_cleanup
Create Date: 2026-05-24 20:05:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_step_progress_cleanup"
down_revision = "0027_step_progress_step_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    # ── step_uuid NOT NULL via CHECK then SET NOT NULL ──────────────────
    # SET NOT NULL on its own takes an ACCESS EXCLUSIVE table lock while
    # postgres scans the whole table to prove no NULLs exist. Adding a
    # CHECK constraint NOT VALID then VALIDATE-ing it in a separate
    # transaction does the scan under a weaker lock that allows reads +
    # writes. The later SET NOT NULL can skip the scan because the
    # validated CHECK already proves the invariant holds. Each step is
    # guarded by an existence check so a partial-failure retry works.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_step_progress_step_uuid_nn'
          ) THEN
            ALTER TABLE step_progress
              ADD CONSTRAINT ck_step_progress_step_uuid_nn
              CHECK (step_uuid IS NOT NULL) NOT VALID;
          END IF;
        END$$;
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_step_progress_step_uuid_nn'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE step_progress
                  VALIDATE CONSTRAINT ck_step_progress_step_uuid_nn;
              END IF;
            END$$;
            """
        )
    op.alter_column("step_progress", "step_uuid", nullable=False)
    op.execute(
        "ALTER TABLE step_progress "
        "DROP CONSTRAINT IF EXISTS ck_step_progress_step_uuid_nn"
    )

    # ── Foreign key NOT VALID then VALIDATE (separate transactions) ────
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_step_progress_step_uuid'
          ) THEN
            ALTER TABLE step_progress
              ADD CONSTRAINT fk_step_progress_step_uuid
              FOREIGN KEY (step_uuid) REFERENCES steps(uuid)
              ON DELETE RESTRICT NOT VALID;
          END IF;
        END$$;
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_step_progress_step_uuid'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE step_progress
                  VALIDATE CONSTRAINT fk_step_progress_step_uuid;
              END IF;
            END$$;
            """
        )

    # ── Drop legacy unique constraint ──────────────────────────────────
    op.execute("ALTER TABLE step_progress DROP CONSTRAINT IF EXISTS uq_user_topic_step")

    # ── New unique constraint via concurrent index then ALTER TABLE ────
    # CREATE UNIQUE INDEX CONCURRENTLY keeps writes flowing; the
    # subsequent ALTER TABLE ... USING INDEX upgrades it to a constraint
    # without rebuilding.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_step_progress_user_step ON step_progress (user_id, step_uuid)"
        )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_step_progress_user_step'
          ) THEN
            ALTER TABLE step_progress
              ADD CONSTRAINT uq_step_progress_user_step
              UNIQUE USING INDEX uq_step_progress_user_step;
          END IF;
        END$$;
        """
    )

    # ── Drop legacy indexes concurrently ───────────────────────────────
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_step_progress_user_topic")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_step_progress_user_phase")

    # ── Drop legacy columns ────────────────────────────────────────────
    op.execute("ALTER TABLE step_progress DROP COLUMN IF EXISTS step_order")
    op.execute("ALTER TABLE step_progress DROP COLUMN IF EXISTS phase_id")
    op.execute("ALTER TABLE step_progress DROP COLUMN IF EXISTS step_id")
    op.execute("ALTER TABLE step_progress DROP COLUMN IF EXISTS topic_id")


def downgrade() -> None:
    op.add_column(
        "step_progress",
        sa.Column("topic_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "step_progress",
        sa.Column("step_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "step_progress",
        sa.Column("phase_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "step_progress",
        sa.Column("step_order", sa.Integer(), nullable=True),
    )

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_step_progress_user_phase ON step_progress (user_id, phase_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_step_progress_user_topic ON step_progress (user_id, topic_id)"
        )

    op.drop_constraint("uq_step_progress_user_step", "step_progress", type_="unique")
    op.create_unique_constraint(
        "uq_user_topic_step",
        "step_progress",
        ["user_id", "topic_id", "step_id"],
    )

    op.drop_constraint(
        "fk_step_progress_step_uuid", "step_progress", type_="foreignkey"
    )
    op.alter_column("step_progress", "step_uuid", nullable=True)
