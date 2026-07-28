"""drop legacy learner-state and database curriculum contract

Why this change: learner state now lives exclusively in
``verification_attempts`` and ``learner_step_completions`` while curriculum
content is served from the packaged artifact. The legacy verification,
submission, step-progress, and curriculum tables are no longer runtime
dependencies.

Schema effect:
- Refuses to run until legacy verification and step state is fully reconciled.
- Removes temporary drain triggers and their SECURITY DEFINER functions.
- Drops migration-provenance columns from ``verification_attempts``.
- Drops ``verification_jobs``, ``submissions``, ``step_progress``, and all five
  database curriculum tables.
- Reapplies least-privilege Functions grants without the provenance column.

This contract migration is intentionally irreversible. A downgrade could
recreate empty legacy tables but cannot recover the dropped learner history,
curriculum shadow, or provenance. Failing loudly is safer than presenting a
false rollback path.

Revision ID: 0055_drop_legacy_curriculum_contract
Revises: 0054_repair_deleted_legacy_job_attempts
Create Date: 2026-07-15
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0055_drop_legacy_curriculum_contract"
down_revision: str | None = "0054_repair_deleted_legacy_job_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SELECT_COLUMNS: tuple[str, ...] = (
    "id",
    "user_id",
    "requirement_uuid",
    "snapshot_source",
    "payload_version",
    "requirement_snapshot",
    "requirement_snapshot_hash",
    "submission_value_kind",
    "submitted_value",
    "github_username_snapshot",
    "cloud_provider",
    "traceparent",
    "outcome",
    "started_at",
    "created_at",
    "completed_at",
    "error_code",
    "validation_message",
    "terminal_source",
    "feedback_json",
)

_UPDATE_COLUMNS: tuple[str, ...] = (
    "outcome",
    "error_code",
    "validation_message",
    "terminal_source",
    "feedback_json",
    "started_at",
    "completed_at",
    "updated_at",
)

_DRAIN_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "unlinked verification jobs",
        """
        SELECT count(*)
        FROM verification_jobs
        WHERE result_submission_id IS NULL
        """,
    ),
    (
        "verification jobs without matching attempts",
        """
        SELECT count(*)
        FROM verification_jobs AS j
        LEFT JOIN verification_attempts AS a
          ON a.legacy_job_id = j.id
        WHERE a.id IS NULL
        """,
    ),
    (
        "active attempts linked to legacy jobs",
        """
        SELECT count(*)
        FROM verification_attempts
        WHERE legacy_job_id IS NOT NULL
          AND outcome IS NULL
        """,
    ),
    (
        "legacy submissions without matching attempts",
        """
        SELECT count(*)
        FROM submissions AS s
        WHERE NOT EXISTS (
            SELECT 1
            FROM verification_attempts AS a
            WHERE a.legacy_submission_id = s.id
        )
        """,
    ),
    (
        "legacy step completions without authoritative rows",
        """
        SELECT count(*)
        FROM step_progress AS p
        WHERE NOT EXISTS (
            SELECT 1
            FROM learner_step_completions AS c
            WHERE c.user_id = p.user_id
              AND c.step_uuid = p.step_uuid
        )
        """,
    ),
    (
        "legacy outcomes that differ from authoritative attempts",
        """
        SELECT count(*)
        FROM verification_jobs AS j
        JOIN submissions AS s
          ON s.id = j.result_submission_id
        JOIN verification_attempts AS a
          ON a.legacy_job_id = j.id
        WHERE a.outcome IS DISTINCT FROM CASE
            WHEN s.is_validated THEN 'succeeded'
            WHEN s.verification_completed THEN 'failed'
            ELSE 'server_error'
        END
        """,
    ),
)


def _verification_functions_role() -> str | None:
    role = os.environ.get("POSTGRES_VERIFICATION_FUNCTIONS_ROLE")
    if not role:
        return None
    if not (role[0].isalpha() or role[0] == "_") or not all(
        char.isalnum() or char == "_" for char in role
    ):
        raise RuntimeError(
            f"POSTGRES_VERIFICATION_FUNCTIONS_ROLE is not a valid identifier: {role!r}"
        )
    return role


def _assert_drain_complete() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    failures: list[str] = []
    for label, query in _DRAIN_CHECKS:
        count = bind.execute(sa.text(query)).scalar_one()
        if count:
            failures.append(f"{label}: {count}")
    if failures:
        detail = "; ".join(failures)
        raise RuntimeError(f"Legacy contract drain is incomplete ({detail})")


def _drop_temporary_bridges() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_terminalize_deleted_legacy_verification_job
        ON verification_jobs
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_bridge_legacy_verification_job_link
        ON verification_jobs
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_bridge_legacy_verification_job_insert
        ON verification_jobs
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            public.terminalize_deleted_legacy_verification_job()
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            public.bridge_legacy_verification_job_to_attempt()
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_mirror_step_progress_to_completions
        ON step_progress
        """
    )
    op.execute("DROP FUNCTION IF EXISTS mirror_step_progress_to_completions()")


def _narrow_functions_grants() -> None:
    role = _verification_functions_role()
    if not role:
        return

    select_columns = ", ".join(_SELECT_COLUMNS)
    update_columns = ", ".join(_UPDATE_COLUMNS)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON verification_attempts FROM "{role}";
                GRANT SELECT ({select_columns})
                    ON verification_attempts TO "{role}";
                GRANT UPDATE ({update_columns})
                    ON verification_attempts TO "{role}";
                REVOKE SELECT (uuid, submission_value_kind)
                    ON requirements FROM "{role}";
            END IF;
        END $$;
        """
    )


def _drop_retired_tables() -> None:
    # PR 9 removes every client before this contract migration can deploy.
    for table_name in (
        "verification_jobs",
        "step_progress",
        "submissions",
        "requirements",
        "learning_objectives",
        "steps",
        "topics",
        "phases",
    ):
        op.execute(
            f"""
            -- squawk-ignore ban-drop-table
            DROP TABLE {table_name}
            """
        )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")

    _assert_drain_complete()
    _drop_temporary_bridges()
    _narrow_functions_grants()

    op.drop_column("verification_attempts", "legacy_job_id")
    op.drop_column("verification_attempts", "legacy_submission_id")

    _drop_retired_tables()


def downgrade() -> None:
    raise NotImplementedError(
        "0055 drops legacy learner history and curriculum data; downgrade is "
        "intentionally unsupported"
    )
