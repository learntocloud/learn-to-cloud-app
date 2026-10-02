"""terminalize attempts when legacy jobs are deleted during drain

Why this change: an older API replica can still delete a failed, unlinked
``verification_jobs`` row during a rolling deployment. Migration 0052 bridges
job inserts and result links, but without a delete bridge that old poller would
leave its matching ``verification_attempts`` row active.

Schema effect:
- Adds a temporary SECURITY DEFINER delete trigger that compare-and-sets the
  matching active attempt to ``server_error`` in the same transaction.

Rollback removes the temporary trigger and function but preserves terminal
attempt outcomes.

Revision ID: 0053_bridge_legacy_job_deletes
Revises: 0052_bridge_legacy_verification_drain
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0053_bridge_legacy_job_deletes"
down_revision: str | None = "0052_bridge_legacy_verification_drain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = "terminalize_deleted_legacy_verification_job"
_TRIGGER = "trg_terminalize_deleted_legacy_verification_job"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.{_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $function$
        BEGIN
            UPDATE public.verification_attempts
            SET outcome = 'server_error',
                started_at = COALESCE(started_at, OLD.created_at),
                completed_at = now(),
                validation_message =
                    'Legacy verification ended before recording a result.',
                error_code = 'server_error',
                terminal_source = 'legacy_job_delete',
                updated_at = now()
            WHERE id = OLD.id
              AND legacy_job_id = OLD.id
              AND outcome IS NULL;

            RETURN OLD;
        END;
        $function$;
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.{_FUNCTION}() FROM PUBLIC")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        AFTER DELETE ON verification_jobs
        FOR EACH ROW EXECUTE FUNCTION public.{_FUNCTION}()
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON verification_jobs")
    op.execute(f"DROP FUNCTION IF EXISTS public.{_FUNCTION}()")
