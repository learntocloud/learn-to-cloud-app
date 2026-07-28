"""narrow Functions role verification_attempts grants to column level

Why this change: PR4 of the verification refactor (the bridge) has the
Functions role read attempts to prepare/reconcile and write only the
result/lifecycle columns to finalize. Revision 0049 granted it table-level
``SELECT, INSERT, UPDATE`` on ``verification_attempts`` as a placeholder; this
revision narrows that to least privilege now that the exact column surface is
known.

Schema effect (Functions role only; no-op when the role env var is unset or
the role does not exist):
- REVOKE ALL ON ``verification_attempts`` (drops the 0049 table-level
  SELECT/INSERT/UPDATE, and INSERT/DELETE the bridge never needs).
- GRANT SELECT on only the identity/snapshot/lifecycle columns the prepare,
  reconcile, and legacy-mirror reads touch.
- GRANT UPDATE on only the lifecycle/result columns prepare and finalize write
  (``started_at``, ``outcome``, ``error_code``, ``validation_message``,
  ``terminal_source``, ``feedback_json``, ``completed_at``, ``updated_at``).
  The immutable user/requirement/snapshot/submitted-value identity columns are
  intentionally excluded, so the role cannot rewrite what an attempt was
  submitted against.
- Leaves the legacy ``submissions`` (SELECT/INSERT) and ``verification_jobs``
  (SELECT/UPDATE) grants untouched: the bridge still mirrors/links legacy rows.

Rollback notes: downgrade REVOKEs the column grants and restores the 0049
table-level ``SELECT, INSERT, UPDATE`` so the chain is reversible.

Revision ID: 0051_narrow_functions_role_attempt_grants
Revises: 0050_verification_attempts_concurrent_indexes
Create Date: 2026-07-14
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0051_narrow_functions_role_attempt_grants"
down_revision: str | None = "0050_verification_attempts_concurrent_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Columns the prepare, reconcile, status, and legacy-mirror reads need. Keep in
# sync with VerificationAttemptRepository's projections.
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
    "legacy_job_id",
)

# Only lifecycle/result columns are writable. No immutable identity column is
# updatable by the Functions role.
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


def _apply_grants(role: str, *, select_cols: str, update_cols: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON verification_attempts FROM "{role}";
                GRANT SELECT ({select_cols})
                    ON verification_attempts TO "{role}";
                GRANT UPDATE ({update_cols})
                    ON verification_attempts TO "{role}";
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    role = _verification_functions_role()
    if not role:
        return
    _apply_grants(
        role,
        select_cols=", ".join(_SELECT_COLUMNS),
        update_cols=", ".join(_UPDATE_COLUMNS),
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    role = _verification_functions_role()
    if not role:
        return
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON verification_attempts FROM "{role}";
                GRANT SELECT, INSERT, UPDATE
                    ON verification_attempts TO "{role}";
            END IF;
        END $$;
        """
    )
