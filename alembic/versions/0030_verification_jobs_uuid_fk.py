"""verification_jobs UUID FK (Phase D.3)

Closes Phase D of #461 / #465: ``verification_jobs`` now references
the curriculum solely by ``requirement_uuid``. Same combined-PR shape
as Phase D.2 (additive + cleanup in one migration) with the same
accepted trade-off: a brief 500s window during pod rollover while
old pods still reference the dropped columns.

## Schema effect

- Adds ``verification_jobs.requirement_uuid UUID``.
- Backfills from ``requirements.id`` (lookup includes soft-deleted
  rows so any in-flight job for a soft-deleted requirement still
  gets a UUID).
- DELETEs rows whose ``requirement_id`` matches no row in
  ``requirements`` at all. Production preflight: 0 such rows.
- Drops the legacy partial unique index
  ``uq_verification_jobs_active_user_requirement_v2``. Replaces with
  ``uq_verification_jobs_active_user_req_uuid`` -- same predicate
  (``result_submission_id IS NULL``) on the new UUID column.
- Drops ``ix_verification_jobs_user_req_created`` and replaces with
  ``ix_verification_jobs_user_req_uuid_created`` covering the
  same latest-per-(user, requirement) lookup.
- Drops ``ix_verification_jobs_user_phase_active`` outright -- its
  ``phase_id`` column is going away and no replacement is needed
  (the in-flight per-user query is rare and covered by the
  active partial unique index).
- ``requirement_uuid`` SET NOT NULL via the CHECK-then-flip pattern
  used in D.1/D.2; FK ``ON DELETE RESTRICT`` added NOT VALID then
  VALIDATEd in a separate transaction.
- Drops legacy columns: ``requirement_id``, ``phase_id``,
  ``submission_type``.

## Production preflight (2026-05-24, after D.2 deploy)

    rows                                       : 246
    rows where requirement_id resolves         : 246
    unresolved requirement_ids                 : 0
    in-flight (result_submission_id IS NULL)   : 0

All rows backfill cleanly; nothing to delete. The 0 in-flight count
also means the partial unique index swap touches no rows.

Revision ID: 0030_verification_jobs_uuid_fk
Create Date: 2026-05-24 21:05:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0030_verification_jobs_uuid_fk"
down_revision = "0029_submissions_uuid_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute(
        "ALTER TABLE verification_jobs ADD COLUMN IF NOT EXISTS requirement_uuid UUID"
    )

    op.execute(
        """
        UPDATE verification_jobs vj
        SET requirement_uuid = r.uuid
        FROM requirements r
        WHERE r.id = vj.requirement_id
        """
    )

    op.execute("DELETE FROM verification_jobs WHERE requirement_uuid IS NULL")

    # ── NOT NULL via CHECK-then-flip ───────────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_verification_jobs_requirement_uuid_nn'
          ) THEN
            ALTER TABLE verification_jobs
              ADD CONSTRAINT ck_verification_jobs_requirement_uuid_nn
              CHECK (requirement_uuid IS NOT NULL) NOT VALID;
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
                WHERE conname = 'ck_verification_jobs_requirement_uuid_nn'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE verification_jobs
                  VALIDATE CONSTRAINT ck_verification_jobs_requirement_uuid_nn;
              END IF;
            END$$;
            """
        )
    op.alter_column("verification_jobs", "requirement_uuid", nullable=False)
    op.execute(
        "ALTER TABLE verification_jobs "
        "DROP CONSTRAINT IF EXISTS ck_verification_jobs_requirement_uuid_nn"
    )

    # ── FK NOT VALID then VALIDATE (separate transactions) ─────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_verification_jobs_requirement_uuid'
          ) THEN
            ALTER TABLE verification_jobs
              ADD CONSTRAINT fk_verification_jobs_requirement_uuid
              FOREIGN KEY (requirement_uuid) REFERENCES requirements(uuid)
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
                WHERE conname = 'fk_verification_jobs_requirement_uuid'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE verification_jobs
                  VALIDATE CONSTRAINT fk_verification_jobs_requirement_uuid;
              END IF;
            END$$;
            """
        )

    # ── Drop legacy indexes concurrently ───────────────────────────────
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "uq_verification_jobs_active_user_requirement_v2"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_verification_jobs_user_req_created"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_verification_jobs_user_phase_active"
        )

    # ── New active partial unique + latest-per-req indexes ─────────────
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_verification_jobs_active_user_req_uuid "
            "ON verification_jobs (user_id, requirement_uuid) "
            "WHERE result_submission_id IS NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_verification_jobs_user_req_uuid_created "
            "ON verification_jobs (user_id, requirement_uuid, created_at)"
        )

    # ── Drop legacy columns ────────────────────────────────────────────
    op.execute("ALTER TABLE verification_jobs DROP COLUMN IF EXISTS submission_type")
    op.execute("ALTER TABLE verification_jobs DROP COLUMN IF EXISTS phase_id")
    op.execute("ALTER TABLE verification_jobs DROP COLUMN IF EXISTS requirement_id")


def downgrade() -> None:
    op.add_column(
        "verification_jobs",
        sa.Column("requirement_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "verification_jobs",
        sa.Column("phase_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "verification_jobs",
        sa.Column("submission_type", sa.String(length=50), nullable=True),
    )

    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "ix_verification_jobs_user_req_uuid_created"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "uq_verification_jobs_active_user_req_uuid"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_verification_jobs_user_phase_active "
            "ON verification_jobs (user_id, phase_id) "
            "WHERE result_submission_id IS NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_verification_jobs_user_req_created "
            "ON verification_jobs (user_id, requirement_id, created_at)"
        )
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_verification_jobs_active_user_requirement_v2 "
            "ON verification_jobs (user_id, requirement_id) "
            "WHERE result_submission_id IS NULL"
        )

    op.drop_constraint(
        "fk_verification_jobs_requirement_uuid",
        "verification_jobs",
        type_="foreignkey",
    )
    op.alter_column("verification_jobs", "requirement_uuid", nullable=True)
