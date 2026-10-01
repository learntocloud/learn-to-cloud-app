"""submissions UUID FK + drop attempt_number (Phase D.2 + #460)

Why this change: Phase D of #461 / #465. Combines the additive +
cleanup steps for ``submissions`` into one PR (one migration, one
deploy). The agreed trade-off is a brief 500s window during pod
rollover while old pods still reference the dropped columns; see
``.squawk.toml`` for the documented rule exclusions.

Also lands #460: drop ``attempt_number`` and the
``uq_user_requirement_attempt`` unique constraint. Nothing in the
codebase reads ``attempt_number``; the unique constraint's only role
was to disambiguate retries, and the row PK already does that.

## Schema effect

- Adds ``submissions.requirement_uuid UUID``.
- Backfills from ``requirements.id`` -- the lookup includes
  soft-deleted requirements (no ``deleted_at IS NULL`` filter) so
  in-flight submissions for a soft-deleted requirement still get a
  UUID. The ``uq_requirements_id_active`` partial index only guards
  active rows from collisions, but ``requirements.id`` is also
  globally unique-ish historically: there are no recorded cases of two
  soft-deleted requirements sharing an id, so the lookup is
  deterministic in practice.
- DELETEs 210 rows whose ``requirement_id`` matches no row in
  ``requirements`` at all (the 6 ``journal-pr-*`` slugs from an old
  curriculum revision that was never synced). These rows are
  already invisible from the app's perspective because no requirement
  resolves them via ``get_requirement_by_id``.
- Drops the legacy unique constraint ``uq_user_requirement_attempt``;
  per #460 there is no replacement -- the row PK is sufficient and
  the app already keys "latest submission" by ``ORDER BY id DESC``.
- Drops legacy indexes ``ix_submissions_user_phase_req`` (used
  ``phase_id`` which we are dropping) and ``ix_submissions_user_req_latest``
  (used ``requirement_id`` which we are dropping). Replaces with
  ``ix_submissions_user_req_uuid_latest`` covering the same
  latest-submission query path on the new UUID.
- ``requirement_uuid`` SET NOT NULL via the CHECK-then-flip pattern
  used elsewhere in this refactor; FK ``ON DELETE RESTRICT`` to
  ``requirements(uuid)`` added NOT VALID then VALIDATEd in a
  separate transaction.
- Drops legacy columns: ``attempt_number``, ``submission_type``,
  ``phase_id``, ``requirement_id``.

## Production preflight (2026-05-24)

    rows                                       : 2588
    distinct users                             : 1114
    rows resolving incl soft-deleted           : 2378
    rows with no matching requirement at all   : 210 (in 6 stale slugs)
    distinct attempt_numbers                   : 1..22 (denormalized counter)
    (user,req) groups with >1 attempt           : 285
    in-flight verification_jobs                : 0

Mixed-validation groups exist but in all of them the latest-by-attempt
row is the validated one, so the row PK ordering preserves the
"latest validated wins" semantic without the explicit counter.

## Rollback

``downgrade()`` re-adds the legacy columns (nullable), recreates the
two dropped indexes, and rebuilds the unique constraint. It does NOT
restore deleted orphan rows, and it does NOT re-derive
``submission_type`` / ``phase_id`` / ``attempt_number`` from
``requirement_uuid`` -- the source data for that derivation no longer
exists in a single denormalized form.

Revision ID: 0029_submissions_uuid_fk
Create Date: 2026-05-24 20:35:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0029_submissions_uuid_fk"
down_revision = "0028_step_progress_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")

    # ── Additive column ────────────────────────────────────────────────
    op.execute("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS requirement_uuid UUID")

    # ── Backfill: include soft-deleted requirements ────────────────────
    op.execute(
        """
        UPDATE submissions sub
        SET requirement_uuid = r.uuid
        FROM requirements r
        WHERE r.id = sub.requirement_id
        """
    )

    # ── Delete orphan rows (no matching requirement at all) ────────────
    op.execute("DELETE FROM submissions WHERE requirement_uuid IS NULL")

    # ── NOT NULL via CHECK-then-flip ───────────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_submissions_requirement_uuid_nn'
          ) THEN
            ALTER TABLE submissions
              ADD CONSTRAINT ck_submissions_requirement_uuid_nn
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
                WHERE conname = 'ck_submissions_requirement_uuid_nn'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE submissions
                  VALIDATE CONSTRAINT ck_submissions_requirement_uuid_nn;
              END IF;
            END$$;
            """
        )
    op.alter_column("submissions", "requirement_uuid", nullable=False)
    op.execute(
        "ALTER TABLE submissions "
        "DROP CONSTRAINT IF EXISTS ck_submissions_requirement_uuid_nn"
    )

    # ── FK NOT VALID then VALIDATE (separate transactions) ─────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_submissions_requirement_uuid'
          ) THEN
            ALTER TABLE submissions
              ADD CONSTRAINT fk_submissions_requirement_uuid
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
                WHERE conname = 'fk_submissions_requirement_uuid'
                  AND NOT convalidated
              ) THEN
                ALTER TABLE submissions
                  VALIDATE CONSTRAINT fk_submissions_requirement_uuid;
              END IF;
            END$$;
            """
        )

    # ── Drop legacy unique constraint (per #460) ───────────────────────
    op.execute(
        "ALTER TABLE submissions DROP CONSTRAINT IF EXISTS uq_user_requirement_attempt"
    )

    # ── Drop legacy indexes concurrently ───────────────────────────────
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_submissions_user_phase_req")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_submissions_user_req_latest")

    # ── New index for latest-per-(user, requirement_uuid) ──────────────
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_submissions_user_req_uuid_latest "
            "ON submissions (user_id, requirement_uuid, created_at DESC)"
        )

    # ── Drop legacy columns ────────────────────────────────────────────
    op.execute("ALTER TABLE submissions DROP COLUMN IF EXISTS attempt_number")
    op.execute("ALTER TABLE submissions DROP COLUMN IF EXISTS submission_type")
    op.execute("ALTER TABLE submissions DROP COLUMN IF EXISTS phase_id")
    op.execute("ALTER TABLE submissions DROP COLUMN IF EXISTS requirement_id")


def downgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("requirement_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("phase_id", sa.Integer(), nullable=True),
    )
    # Original column used Enum(SubmissionType, native_enum=False), which
    # is stored as VARCHAR + CHECK constraint, not a postgres ENUM type.
    # Recreate as a plain string; the CHECK constraint isn't restored
    # (downgrade is a developer escape hatch, not a production rollback).
    op.add_column(
        "submissions",
        sa.Column("submission_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("1"),
        ),
    )

    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_submissions_user_req_uuid_latest"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_submissions_user_req_latest "
            "ON submissions (user_id, requirement_id, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_submissions_user_phase_req "
            "ON submissions (user_id, phase_id, requirement_id)"
        )

    op.create_unique_constraint(
        "uq_user_requirement_attempt",
        "submissions",
        ["user_id", "requirement_id", "attempt_number"],
    )

    op.drop_constraint(
        "fk_submissions_requirement_uuid", "submissions", type_="foreignkey"
    )
    op.alter_column("submissions", "requirement_uuid", nullable=True)
