"""add verification_attempts and learner_step_completions (expand)

Why this change: PR3 of the verification-schema refactor. Introduces the
two curriculum-decoupled tables that later PRs migrate onto:
``verification_attempts`` (one row per attempt, keyed by its Durable
orchestration id) and ``learner_step_completions`` (step completions
keyed by ``step_uuid`` with no FK to the curriculum). This is an
EXPAND-ONLY step: existing readers/writers keep using ``step_progress``,
``submissions`` and ``verification_jobs`` unchanged. A temporary trigger
mirrors ``step_progress`` INSERT/DELETE into ``learner_step_completions``
so the new table stays consistent while legacy revisions remain the
writers; the explicit dual-writes land in later PRs.

Schema effect:
- Creates ``learner_step_completions`` (composite PK ``(user_id,
  step_uuid)``) and backfills every ``step_progress`` row.
- Creates ``verification_attempts`` with the identity/snapshot,
  submitted-value, and lifecycle columns plus their CHECK constraints,
  and backfills it from ``verification_jobs`` + ``submissions``.
- Installs the ``step_progress`` mirroring trigger (idempotent) before
  the backfill so no concurrent legacy write is missed.
- Grants the verification Functions role SELECT/INSERT/UPDATE on
  ``verification_attempts`` (table-level for now; a later bridge narrows
  to column privileges).

This revision runs entirely inside one transaction (no
``autocommit_block``) so it stamps atomically. The active/succeeded/latest
indexes are created CONCURRENTLY in the follow-up revision 0050 so a
failed/retried index build never leaves this revision half-applied.

Backfill rules:
- Linked verification_jobs -> attempt id = job id, terminal outcome
  derived from the linked submission (is_validated -> succeeded, else
  verification_completed -> failed, else server_error). Every job is
  preserved, including multiple jobs linked to one submission.
- Unlinked verification_jobs -> active attempt (outcome/completed_at
  NULL) for the PR4 reconciler.
- Submission with no job -> deterministic UUIDv5 attempt id from a fixed
  namespace + legacy submission id.
- Migrated rows use ``snapshot_source='reconstructed'`` and only claim a
  requirement snapshot that can be honestly reconstructed from the
  current ``requirements`` row; artifact metadata stays NULL.

Safety:
- Preflight aborts (rather than silently dropping data) if unlinked jobs
  already violate the one-active-attempt invariant that revision 0050's
  partial unique index enforces, or if a derived orphan id collides with
  an unrelated existing attempt.
- Backfill INSERTs are ``ON CONFLICT (id) DO NOTHING`` and the trigger is
  ``DROP ... IF EXISTS`` + ``CREATE OR REPLACE`` so a re-run is a no-op.

Rollback notes: downgrade drops the trigger, function, and both tables
(grants go with them; the concurrent indexes are dropped first by
revision 0050's downgrade). Backfilled history is not preserved on
downgrade because the legacy tables still hold the source rows.

Revision ID: 0049_add_verification_attempts_and_step_completions
Revises: 0048_validate_deployment_architecture_type
Create Date: 2026-07-14
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from learn_to_cloud_shared.verification_provenance import (
    attempt_id_for_orphan_submission,
    derive_outcome,
)
from sqlalchemy.dialects.postgresql import JSONB

from alembic import context, op

revision: str = "0049_add_verification_attempts_and_step_completions"
down_revision: str | None = "0048_validate_deployment_architecture_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MIRROR_FUNCTION = "mirror_step_progress_to_completions"
_MIRROR_TRIGGER = "trg_mirror_step_progress_to_completions"


def _verification_functions_role() -> str | None:
    """Return the validated Functions DB role name, or None when unset."""
    role = os.environ.get("POSTGRES_VERIFICATION_FUNCTIONS_ROLE")
    if not role:
        return None
    if not (role[0].isalpha() or role[0] == "_") or not all(
        c.isalnum() or c == "_" for c in role
    ):
        raise RuntimeError(
            f"POSTGRES_VERIFICATION_FUNCTIONS_ROLE is not a valid identifier: {role!r}"
        )
    return role


def _create_tables() -> None:
    op.create_table(
        "learner_step_completions",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("step_uuid", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "user_id", "step_uuid", name="pk_learner_step_completions"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learner_step_completions_user_id",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "verification_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("requirement_uuid", sa.Uuid(as_uuid=True), nullable=False),
        # Identity / snapshot. Text/BigInteger throughout to satisfy squawk's
        # prefer-text-field and prefer-bigint-over-int rules for new columns.
        sa.Column("artifact_schema_version", sa.BigInteger(), nullable=True),
        sa.Column("curriculum_version", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("requirement_snapshot", JSONB(), nullable=True),
        sa.Column("requirement_snapshot_hash", sa.Text(), nullable=True),
        sa.Column("snapshot_source", sa.Text(), nullable=False),
        sa.Column("payload_version", sa.BigInteger(), nullable=True),
        # Submitted identity / value.
        sa.Column("github_username_snapshot", sa.Text(), nullable=True),
        sa.Column("submission_value_kind", sa.Text(), nullable=False),
        sa.Column("submitted_value", sa.Text(), nullable=False),
        sa.Column("cloud_provider", sa.Text(), nullable=True),
        sa.Column("traceparent", sa.Text(), nullable=True),
        # Lifecycle / result.
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback_json", JSONB(), nullable=True),
        sa.Column("validation_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("terminal_source", sa.Text(), nullable=True),
        # Temporary migration provenance.
        sa.Column("legacy_job_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("legacy_submission_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_verification_attempts"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_verification_attempts_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "submission_value_kind IN ('github_url', 'token', 'deployed_url', 'text')",
            name="ck_verification_attempts_value_kind",
        ),
        sa.CheckConstraint(
            "length(btrim(submitted_value)) > 0",
            name="ck_verification_attempts_submitted_value_nonempty",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN "
            "('succeeded', 'failed', 'server_error', 'cancelled')",
            name="ck_verification_attempts_outcome",
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (completed_at IS NULL)",
            name="ck_verification_attempts_outcome_completed_at",
        ),
        sa.CheckConstraint(
            "snapshot_source IN ('submitted', 'reconstructed')",
            name="ck_verification_attempts_snapshot_source",
        ),
        sa.CheckConstraint(
            "snapshot_source = 'reconstructed' OR ("
            "requirement_snapshot IS NOT NULL "
            "AND requirement_snapshot_hash IS NOT NULL)",
            name="ck_verification_attempts_submitted_snapshot_present",
        ),
    )


def _install_mirror_trigger() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_MIRROR_FUNCTION}()
        RETURNS trigger AS $$
        BEGIN
            IF (TG_OP = 'INSERT') THEN
                INSERT INTO learner_step_completions
                    (user_id, step_uuid, completed_at)
                VALUES (NEW.user_id, NEW.step_uuid, NEW.completed_at)
                ON CONFLICT (user_id, step_uuid) DO NOTHING;
                RETURN NEW;
            ELSIF (TG_OP = 'DELETE') THEN
                DELETE FROM learner_step_completions
                WHERE user_id = OLD.user_id
                  AND step_uuid = OLD.step_uuid;
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(f"DROP TRIGGER IF EXISTS {_MIRROR_TRIGGER} ON step_progress")
    op.execute(
        f"""
        CREATE TRIGGER {_MIRROR_TRIGGER}
        AFTER INSERT OR DELETE ON step_progress
        FOR EACH ROW EXECUTE FUNCTION {_MIRROR_FUNCTION}();
        """
    )


def _preflight_active_uniqueness() -> None:
    """Abort if unlinked jobs already break the one-active-attempt rule."""
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT user_id, requirement_uuid, count(*) AS n
            FROM verification_jobs
            WHERE result_submission_id IS NULL
            GROUP BY user_id, requirement_uuid
            HAVING count(*) > 1
            """
        )
    ).all()
    if result:
        offenders = ", ".join(
            f"(user_id={row.user_id}, requirement_uuid={row.requirement_uuid}: "
            f"{row.n} active jobs)"
            for row in result
        )
        raise RuntimeError(
            "Cannot backfill verification_attempts: unlinked verification_jobs "
            "already violate the one-active-attempt-per-(user, requirement) "
            f"invariant: {offenders}. Resolve the duplicates before migrating."
        )


def _backfill_step_completions() -> None:
    op.execute(
        """
        INSERT INTO learner_step_completions (user_id, step_uuid, completed_at)
        SELECT user_id, step_uuid, completed_at
        FROM step_progress
        ON CONFLICT (user_id, step_uuid) DO NOTHING
        """
    )


def _backfill_job_attempts() -> None:
    op.execute(
        """
        INSERT INTO verification_attempts (
            id, user_id, requirement_uuid,
            artifact_schema_version, curriculum_version, content_hash,
            requirement_snapshot, requirement_snapshot_hash,
            snapshot_source, payload_version,
            github_username_snapshot, submission_value_kind, submitted_value,
            cloud_provider, traceparent,
            outcome, started_at, completed_at, feedback_json, validation_message,
            error_code, terminal_source, legacy_job_id, legacy_submission_id,
            created_at, updated_at
        )
        SELECT
            vj.id,
            vj.user_id,
            vj.requirement_uuid,
            NULL, NULL, NULL,
            CASE WHEN r.uuid IS NOT NULL THEN jsonb_build_object(
                'uuid', r.uuid::text,
                'slug', r.slug,
                'name', r.name,
                'submission_type', r.submission_type,
                'submission_value_kind', r.submission_value_kind,
                'reconstructed', true
            ) ELSE NULL END,
            NULL,
            'reconstructed',
            NULL,
            vj.extracted_username,
            vj.submission_value_kind,
            vj.submitted_value,
            vj.cloud_provider,
            vj.traceparent,
            CASE
                WHEN vj.result_submission_id IS NULL THEN NULL
                WHEN s.is_validated THEN 'succeeded'
                WHEN s.verification_completed THEN 'failed'
                ELSE 'server_error'
            END,
            vj.created_at,
            CASE
                WHEN vj.result_submission_id IS NULL THEN NULL
                ELSE COALESCE(
                    s.validated_at, s.updated_at, s.created_at, vj.created_at, now()
                )
            END,
            CASE WHEN vj.result_submission_id IS NULL THEN NULL
                 ELSE s.feedback_json END,
            CASE WHEN vj.result_submission_id IS NULL THEN NULL
                 ELSE s.validation_message END,
            NULL,
            CASE WHEN vj.result_submission_id IS NULL THEN NULL
                 ELSE 'migration' END,
            vj.id,
            vj.result_submission_id,
            COALESCE(vj.created_at, now()),
            COALESCE(vj.updated_at, vj.created_at, now())
        FROM verification_jobs vj
        LEFT JOIN submissions s ON s.id = vj.result_submission_id
        LEFT JOIN requirements r ON r.uuid = vj.requirement_uuid
        ON CONFLICT (id) DO NOTHING
        """
    )


def _orphan_attempts_table() -> sa.TableClause:
    return sa.table(
        "verification_attempts",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("user_id", sa.BigInteger()),
        sa.column("requirement_uuid", sa.Uuid(as_uuid=True)),
        sa.column("requirement_snapshot", JSONB()),
        sa.column("snapshot_source", sa.Text()),
        sa.column("github_username_snapshot", sa.Text()),
        sa.column("submission_value_kind", sa.Text()),
        sa.column("submitted_value", sa.Text()),
        sa.column("cloud_provider", sa.Text()),
        sa.column("outcome", sa.Text()),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        sa.column("feedback_json", JSONB()),
        sa.column("validation_message", sa.Text()),
        sa.column("terminal_source", sa.Text()),
        sa.column("legacy_submission_id", sa.BigInteger()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _backfill_orphan_submission_attempts() -> None:
    """Backfill attempts for submissions that never had a job.

    Uses a deterministic UUIDv5 id so the mapping is stable and
    re-runnable. Runs online only: the ``--sql`` render can't read rows to
    compute the ids, and these INSERTs only touch the brand-new
    ``verification_attempts`` table, so skipping them there is safe.
    """
    if context.is_offline_mode():
        op.execute(
            "-- orphan-submission attempt backfill runs online only "
            "(UUIDv5 ids are computed in Python)"
        )
        return

    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT
                    s.id AS submission_id,
                    s.user_id,
                    s.requirement_uuid,
                    s.extracted_username,
                    s.submission_value_kind,
                    s.submitted_value,
                    s.cloud_provider,
                    s.is_validated,
                    s.verification_completed,
                    s.validated_at,
                    s.updated_at,
                    s.created_at,
                    s.feedback_json,
                    s.validation_message,
                    r.uuid AS r_uuid,
                    r.slug AS r_slug,
                    r.name AS r_name,
                    r.submission_type AS r_submission_type,
                    r.submission_value_kind AS r_value_kind
                FROM submissions s
                LEFT JOIN requirements r ON r.uuid = s.requirement_uuid
                WHERE NOT EXISTS (
                    SELECT 1 FROM verification_jobs vj
                    WHERE vj.result_submission_id = s.id
                )
                """
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return

    computed = {
        attempt_id_for_orphan_submission(row["submission_id"]): row for row in rows
    }

    # Collision preflight: any pre-existing attempt sharing a derived id must
    # be the same orphan (idempotent re-run). Otherwise abort rather than
    # silently discard either row.
    existing = bind.execute(
        sa.text(
            """
            SELECT id, legacy_submission_id
            FROM verification_attempts
            WHERE id = ANY(:ids)
            """
        ),
        {"ids": list(computed.keys())},
    ).all()
    existing_ids: set = set()
    for existing_row in existing:
        source = computed[existing_row.id]
        if existing_row.legacy_submission_id != source["submission_id"]:
            raise RuntimeError(
                "Derived orphan-submission attempt id "
                f"{existing_row.id} collides with an unrelated attempt "
                f"(existing legacy_submission_id="
                f"{existing_row.legacy_submission_id}, "
                f"backfill submission_id={source['submission_id']}). Aborting."
            )
        existing_ids.add(existing_row.id)

    to_insert = []
    for attempt_id, row in computed.items():
        if attempt_id in existing_ids:
            continue
        completed_at = row["validated_at"] or row["updated_at"] or row["created_at"]
        snapshot = None
        if row["r_uuid"] is not None:
            snapshot = {
                "uuid": str(row["r_uuid"]),
                "slug": row["r_slug"],
                "name": row["r_name"],
                "submission_type": row["r_submission_type"],
                "submission_value_kind": row["r_value_kind"],
                "reconstructed": True,
            }
        to_insert.append(
            {
                "id": attempt_id,
                "user_id": row["user_id"],
                "requirement_uuid": row["requirement_uuid"],
                "requirement_snapshot": snapshot,
                "snapshot_source": "reconstructed",
                "github_username_snapshot": row["extracted_username"],
                "submission_value_kind": row["submission_value_kind"],
                "submitted_value": row["submitted_value"],
                "cloud_provider": row["cloud_provider"],
                "outcome": derive_outcome(
                    is_validated=row["is_validated"],
                    verification_completed=row["verification_completed"],
                ).value,
                "started_at": row["created_at"],
                "completed_at": completed_at,
                "feedback_json": row["feedback_json"],
                "validation_message": row["validation_message"],
                "terminal_source": "migration",
                "legacy_submission_id": row["submission_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"] or row["created_at"],
            }
        )

    if to_insert:
        bind.execute(sa.insert(_orphan_attempts_table()), to_insert)


def _grant_functions_role() -> None:
    role = _verification_functions_role()
    if not role:
        return
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT SELECT, INSERT, UPDATE
                ON verification_attempts
                TO "{role}";
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")

    _create_tables()
    # Install the mirror trigger BEFORE backfilling step completions so
    # there is no window where a concurrent legacy write to step_progress
    # is missed: any row the trigger races ahead of is still picked up by
    # the ON CONFLICT DO NOTHING backfill, and vice versa.
    _install_mirror_trigger()
    _backfill_step_completions()

    _preflight_active_uniqueness()
    _backfill_job_attempts()
    _backfill_orphan_submission_attempts()

    _grant_functions_role()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    op.execute(f"DROP TRIGGER IF EXISTS {_MIRROR_TRIGGER} ON step_progress")
    op.execute(f"DROP FUNCTION IF EXISTS {_MIRROR_FUNCTION}()")

    # Dropping the tables removes their role grants. The concurrent indexes
    # are owned by revision 0050 and dropped by its downgrade before this
    # revision runs.
    op.drop_table("verification_attempts")
    op.drop_table("learner_step_completions")
