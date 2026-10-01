"""drop unused verification attempt traceparent

Why this change: runtime trace correlation flows through HTTP and Durable
OpenTelemetry context. The copied ``traceparent`` value on
``verification_attempts`` is never read for propagation or business behavior.

Schema effect:
- Removes ``verification_attempts.traceparent``.
- Reapplies the Functions role's column grants without the removed column.

Downgrade recreates the nullable column and restores its prior SELECT grant.
Previously stored values cannot be recovered.

Revision ID: 0057_drop_verification_attempt_traceparent
Revises: 0056_add_community_activity_indexes
Create Date: 2026-08-25
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_drop_verification_attempt_traceparent"
down_revision: str | None = "0056_add_community_activity_indexes"
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
    "outcome",
    "started_at",
    "created_at",
    "completed_at",
    "error_code",
    "validation_message",
    "terminal_source",
    "feedback_json",
)

_SELECT_COLUMNS_WITH_TRACEPARENT: tuple[str, ...] = (
    *_SELECT_COLUMNS[:11],
    "traceparent",
    *_SELECT_COLUMNS[11:],
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


def _verification_functions_role() -> str | None:
    """Return the validated Functions database role name."""
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


def _apply_functions_grants(role: str, select_columns: tuple[str, ...]) -> None:
    select_list = ", ".join(select_columns)
    update_list = ", ".join(_UPDATE_COLUMNS)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON verification_attempts FROM "{role}";
                GRANT SELECT ({select_list})
                    ON verification_attempts TO "{role}";
                GRANT UPDATE ({update_list})
                    ON verification_attempts TO "{role}";
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    """Drop the unused trace context copy and keep grants least-privileged."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    role = _verification_functions_role()
    if role:
        _apply_functions_grants(role, _SELECT_COLUMNS)
    op.drop_column("verification_attempts", "traceparent")


def downgrade() -> None:
    """Restore an empty traceparent column and its prior SELECT grant."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.add_column(
        "verification_attempts",
        sa.Column("traceparent", sa.Text(), nullable=True),
    )
    role = _verification_functions_role()
    if role:
        _apply_functions_grants(role, _SELECT_COLUMNS_WITH_TRACEPARENT)
