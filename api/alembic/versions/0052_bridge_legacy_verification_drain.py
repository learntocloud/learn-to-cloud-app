"""bridge legacy verification results during the drain window

Why this change: legacy API replicas and already-running legacy Durable
orchestrations can write ``verification_jobs`` after the original point-in-time
backfill. Without a database bridge, those jobs can remain missing from
``verification_attempts`` or leave an attempt active after a linked submission
was persisted.

Schema effect:
- Backfills jobs missed after migration 0049.
- Finalizes active attempts from linked legacy submissions.
- Adds temporary insert/link triggers so rolling-deployment writes cannot open
  another gap.
- Uses a locked-down SECURITY DEFINER trigger because the Functions role has
  intentionally narrow column grants on ``verification_attempts``.

Rollback removes the temporary triggers and function but preserves repaired
attempt rows and terminal outcomes.

Revision ID: 0052_bridge_legacy_verification_drain
Revises: 0051_narrow_functions_role_attempt_grants
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0052_bridge_legacy_verification_drain"
down_revision: str | None = "0051_narrow_functions_role_attempt_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = "bridge_legacy_verification_job_to_attempt"
_INSERT_TRIGGER = "trg_bridge_legacy_verification_job_insert"
_LINK_TRIGGER = "trg_bridge_legacy_verification_job_link"

_ATTEMPT_COLUMNS = """
    id, user_id, requirement_uuid,
    artifact_schema_version, curriculum_version, content_hash,
    requirement_snapshot, requirement_snapshot_hash,
    snapshot_source, payload_version,
    github_username_snapshot, submission_value_kind, submitted_value,
    cloud_provider, traceparent,
    outcome, started_at, completed_at, feedback_json, validation_message,
    error_code, terminal_source, legacy_job_id, legacy_submission_id,
    created_at, updated_at
"""

_JOB_ATTEMPT_SELECT = """
    vj.id,
    vj.user_id,
    vj.requirement_uuid,
    NULL, NULL, NULL,
    NULL, NULL,
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
            s.validated_at,
            s.updated_at,
            s.created_at,
            vj.updated_at,
            vj.created_at,
            now()
        )
    END,
    CASE
        WHEN vj.result_submission_id IS NULL THEN NULL
        ELSE s.feedback_json
    END,
    CASE
        WHEN vj.result_submission_id IS NULL THEN NULL
        ELSE s.validation_message
    END,
    CASE
        WHEN vj.result_submission_id IS NULL THEN NULL
        WHEN s.is_validated THEN 'verification_succeeded'
        WHEN s.verification_completed THEN 'validation_failed'
        ELSE 'verification_incomplete'
    END,
    CASE
        WHEN vj.result_submission_id IS NULL THEN NULL
        ELSE 'legacy_orchestrator'
    END,
    vj.id,
    vj.result_submission_id,
    COALESCE(vj.created_at, now()),
    COALESCE(vj.updated_at, vj.created_at, now())
"""


def _backfill_and_finalize() -> None:
    op.execute(
        f"""
        INSERT INTO verification_attempts ({_ATTEMPT_COLUMNS})
        SELECT {_JOB_ATTEMPT_SELECT}
        FROM verification_jobs vj
        LEFT JOIN submissions s ON s.id = vj.result_submission_id
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE verification_attempts AS a
        SET outcome = CASE
                WHEN s.is_validated THEN 'succeeded'
                WHEN s.verification_completed THEN 'failed'
                ELSE 'server_error'
            END,
            started_at = COALESCE(a.started_at, vj.created_at),
            completed_at = COALESCE(
                s.validated_at,
                s.updated_at,
                s.created_at,
                vj.updated_at,
                vj.created_at,
                now()
            ),
            feedback_json = s.feedback_json,
            validation_message = s.validation_message,
            error_code = CASE
                WHEN s.is_validated THEN 'verification_succeeded'
                WHEN s.verification_completed THEN 'validation_failed'
                ELSE 'verification_incomplete'
            END,
            terminal_source = 'legacy_orchestrator',
            legacy_submission_id = s.id,
            updated_at = COALESCE(
                s.updated_at,
                s.created_at,
                vj.updated_at,
                vj.created_at,
                now()
            )
        FROM verification_jobs vj
        JOIN submissions s ON s.id = vj.result_submission_id
        WHERE a.legacy_job_id = vj.id
          AND a.outcome IS NULL
        """
    )


def _install_bridge() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.{_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $function$
        BEGIN
            INSERT INTO public.verification_attempts ({_ATTEMPT_COLUMNS})
            SELECT {_JOB_ATTEMPT_SELECT}
            FROM (SELECT NEW.*) AS vj
            LEFT JOIN public.submissions s
              ON s.id = vj.result_submission_id
            ON CONFLICT DO NOTHING;

            IF NEW.result_submission_id IS NOT NULL THEN
                UPDATE public.verification_attempts AS a
                SET outcome = CASE
                        WHEN s.is_validated THEN 'succeeded'
                        WHEN s.verification_completed THEN 'failed'
                        ELSE 'server_error'
                    END,
                    started_at = COALESCE(a.started_at, NEW.created_at),
                    completed_at = COALESCE(
                        s.validated_at,
                        s.updated_at,
                        s.created_at,
                        NEW.updated_at,
                        NEW.created_at,
                        now()
                    ),
                    feedback_json = s.feedback_json,
                    validation_message = s.validation_message,
                    error_code = CASE
                        WHEN s.is_validated THEN 'verification_succeeded'
                        WHEN s.verification_completed THEN 'validation_failed'
                        ELSE 'verification_incomplete'
                    END,
                    terminal_source = 'legacy_orchestrator',
                    legacy_submission_id = s.id,
                    updated_at = COALESCE(
                        s.updated_at,
                        s.created_at,
                        NEW.updated_at,
                        NEW.created_at,
                        now()
                    )
                FROM public.submissions s
                WHERE a.legacy_job_id = NEW.id
                  AND a.outcome IS NULL
                  AND s.id = NEW.result_submission_id;
            END IF;

            RETURN NEW;
        END;
        $function$;
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.{_FUNCTION}() FROM PUBLIC")
    op.execute(
        f"""
        CREATE TRIGGER {_INSERT_TRIGGER}
        AFTER INSERT ON verification_jobs
        FOR EACH ROW EXECUTE FUNCTION public.{_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_LINK_TRIGGER}
        AFTER UPDATE OF result_submission_id ON verification_jobs
        FOR EACH ROW
        WHEN (NEW.result_submission_id IS DISTINCT FROM OLD.result_submission_id)
        EXECUTE FUNCTION public.{_FUNCTION}()
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")

    _install_bridge()
    _backfill_and_finalize()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.execute(f"DROP TRIGGER IF EXISTS {_LINK_TRIGGER} ON verification_jobs")
    op.execute(f"DROP TRIGGER IF EXISTS {_INSERT_TRIGGER} ON verification_jobs")
    op.execute(f"DROP FUNCTION IF EXISTS public.{_FUNCTION}()")
