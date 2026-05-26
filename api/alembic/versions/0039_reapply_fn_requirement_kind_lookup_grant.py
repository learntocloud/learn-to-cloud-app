"""reapply Functions role requirement kind lookup grant

Revision ID: 0039_reapply_fn_requirement_kind_lookup_grant
Revises: 0038_grant_fn_requirement_kind_lookup
Create Date: 2026-05-26
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0039_reapply_fn_requirement_kind_lookup_grant"
down_revision: str | None = "0038_grant_fn_requirement_kind_lookup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIRED_COLUMNS = "uuid, submission_value_kind"
_ENV_VAR = "POSTGRES_VERIFICATION_FUNCTIONS_ROLE"


def upgrade() -> None:
    role = _verification_functions_role()
    _grant_requirement_lookup(role)


def downgrade() -> None:
    role = _verification_functions_role()
    _revoke_requirement_lookup(role)


def _grant_requirement_lookup(role: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT SELECT ({_REQUIRED_COLUMNS})
                ON requirements
                TO "{role}";
            END IF;
        END $$;
        """
    )


def _revoke_requirement_lookup(role: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE SELECT ({_REQUIRED_COLUMNS})
                ON requirements
                FROM "{role}";
            END IF;
        END $$;
        """
    )


def _verification_functions_role() -> str:
    role = os.environ.get(_ENV_VAR)
    if not role:
        raise RuntimeError(f"{_ENV_VAR} must be set before running this migration")
    if not (role[0].isalpha() or role[0] == "_") or not all(
        c.isalnum() or c == "_" for c in role
    ):
        raise RuntimeError(f"{_ENV_VAR} is not a valid identifier: {role!r}")
    return role
