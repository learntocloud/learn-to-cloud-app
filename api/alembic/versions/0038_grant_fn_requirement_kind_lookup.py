"""grant Functions role requirement kind lookup

Revision ID: 0038_grant_fn_requirement_kind_lookup
Revises: 0037_validate_typed_submitted_value_constraints
Create Date: 2026-05-26
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0038_grant_fn_requirement_kind_lookup"
down_revision: str | None = "0037_validate_typed_submitted_value_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIRED_COLUMNS = "uuid, submission_value_kind"


def upgrade() -> None:
    role = _verification_functions_role()
    if not role:
        return

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


def downgrade() -> None:
    role = _verification_functions_role()
    if not role:
        return

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


def _verification_functions_role() -> str | None:
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
