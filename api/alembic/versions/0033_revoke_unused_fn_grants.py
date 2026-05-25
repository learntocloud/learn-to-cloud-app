"""revoke Functions role grants on curriculum + users tables

Phase E follow-up (#467): after the curriculum-decoupling refactor,
the verification Functions app no longer reads ``users`` or any
curriculum table -- the requirement definition and ``github_username``
snapshot travel with the orchestration payload. Revoke the now-unused
SELECT grants so the Functions role's effective surface matches what
the code actually uses.

The role name is read from ``POSTGRES_VERIFICATION_FUNCTIONS_ROLE`` at
migration time. When the env var is missing (local dev with the
``postgres`` superuser) or the role doesn't exist, the migration
no-ops cleanly. Same idempotency story as the existing migrations.

Schema effect:
- REVOKE SELECT ON users, curriculum_phases, topics, steps,
  learning_objectives, requirements FROM the Functions role.
- Retains: SELECT/INSERT on submissions, SELECT/UPDATE on verification_jobs.

Revision ID: 0033_revoke_unused_fn_grants
Revises: 0032_feedback_json_jsonb
Create Date: 2026-05-25
"""

import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033_revoke_unused_fn_grants"
down_revision: str | None = "0032_feedback_json_jsonb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REVOKE_TABLES = (
    "users",
    "curriculum_phases",
    "topics",
    "steps",
    "learning_objectives",
    "requirements",
)


def upgrade() -> None:
    role = os.environ.get("POSTGRES_VERIFICATION_FUNCTIONS_ROLE")
    if not role:
        return
    # Validate role name: PostgreSQL identifier rules. The migration job
    # sets this from a Terraform local; defense in depth against a
    # mistakenly-set env var.
    if not all(c.isalnum() or c == "_" for c in role) or not role[0].isalpha():
        raise RuntimeError(
            f"POSTGRES_VERIFICATION_FUNCTIONS_ROLE is not a valid identifier: {role!r}"
        )
    tables = ", ".join(_REVOKE_TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE SELECT ON {tables} FROM "{role}";
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    role = os.environ.get("POSTGRES_VERIFICATION_FUNCTIONS_ROLE")
    if not role:
        return
    if not all(c.isalnum() or c == "_" for c in role) or not role[0].isalpha():
        raise RuntimeError(
            f"POSTGRES_VERIFICATION_FUNCTIONS_ROLE is not a valid identifier: {role!r}"
        )
    tables = ", ".join(_REVOKE_TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT SELECT ON {tables} TO "{role}";
            END IF;
        END $$;
        """
    )
