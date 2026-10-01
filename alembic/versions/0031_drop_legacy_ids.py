"""drop legacy_id, rename requirements.id to slug (Phase E follow-up)

Phase E cleanup: the curriculum tables grew transitional ``legacy_id``
columns during Phases B–D so user-state backfills could resolve their
old string keys against curriculum rows. With all user-state tables
now referencing curriculum via UUID FKs (D.1c/D.2/D.3), the
``legacy_id`` columns serve no remaining purpose. This migration drops
them and renames ``requirements.id`` to ``requirements.slug`` to bring
its naming in line with ``phases.slug`` / ``topics.slug`` /
``steps.slug``.

Schema effect:
- ``phases.legacy_id`` (the int 0..6, redundant with ``order``): DROP.
- ``topics.legacy_id`` (the ``phase0-topic4`` composite, no remaining
  readers after the public read path moved to ``slug``): DROP.
- ``learning_objectives.legacy_id`` (never read outside the sync write
  and one validator error message): DROP.
- ``steps.legacy_id`` -> RENAME to ``slug``. Still the same kebab-case
  human-readable string (e.g. ``step-intro``,
  ``phase5-topic5-practice-export-telemetry-cloud-provider``).
- ``requirements.id`` -> RENAME to ``slug``. Drops the partial unique
  indexes ``uq_requirements_phase_id_active`` and
  ``uq_requirements_id_active``, recreates them as
  ``uq_requirements_phase_slug_active`` and
  ``uq_requirements_slug_active`` on the new column.

The renames go through ``ALTER TABLE ... RENAME COLUMN``, which is a
metadata-only operation under ``ACCESS EXCLUSIVE`` -- fast, no data
copy. Index renames likewise.

Every DDL is idempotent.

Rollback notes: ``downgrade()`` re-adds the dropped legacy_id columns
as nullable and reverses the renames. It does NOT repopulate the
dropped values; those were derived from YAML and are not preserved
anywhere else. Downgrade is a developer escape hatch, not a
production rollback path.

Revision ID: 0031_drop_legacy_ids
Create Date: 2026-05-24 21:55:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_drop_legacy_ids"
down_revision = "0030_verification_jobs_uuid_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '1min'")

    # ── Drop legacy_id columns ────────────────────────────────────────
    op.execute("ALTER TABLE phases DROP COLUMN IF EXISTS legacy_id")
    op.execute("ALTER TABLE topics DROP COLUMN IF EXISTS legacy_id")
    op.execute("ALTER TABLE learning_objectives DROP COLUMN IF EXISTS legacy_id")

    # ── Rename steps.legacy_id -> slug ────────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'steps' AND column_name = 'legacy_id'
          ) THEN
            ALTER TABLE steps RENAME COLUMN legacy_id TO slug;
          END IF;
        END$$;
        """
    )

    # ── Rename requirements.id -> slug + rebuild unique indexes ───────
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'requirements' AND column_name = 'id'
          ) THEN
            ALTER TABLE requirements RENAME COLUMN id TO slug;
          END IF;
        END$$;
        """
    )
    # Old partial unique indexes referenced the column name "id"; even
    # though postgres internally tracks them by attnum, the names are
    # human breadcrumbs we want to keep consistent with the new column
    # name. Drop concurrently to avoid blocking writes, rebuild
    # concurrently against ``slug``.
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_requirements_phase_id_active")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_requirements_id_active")
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_requirements_phase_slug_active "
            "ON requirements (phase_uuid, slug) "
            "WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_requirements_slug_active "
            "ON requirements (slug) "
            "WHERE deleted_at IS NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_requirements_slug_active")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS uq_requirements_phase_slug_active"
        )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'requirements' AND column_name = 'slug'
          ) THEN
            ALTER TABLE requirements RENAME COLUMN slug TO id;
          END IF;
        END$$;
        """
    )

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_requirements_id_active "
            "ON requirements (id) "
            "WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_requirements_phase_id_active "
            "ON requirements (phase_uuid, id) "
            "WHERE deleted_at IS NULL"
        )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'steps' AND column_name = 'slug'
          ) THEN
            ALTER TABLE steps RENAME COLUMN slug TO legacy_id;
          END IF;
        END$$;
        """
    )

    op.add_column(
        "learning_objectives",
        sa.Column("legacy_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "topics",
        sa.Column("legacy_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "phases",
        sa.Column("legacy_id", sa.BigInteger(), nullable=True),
    )
