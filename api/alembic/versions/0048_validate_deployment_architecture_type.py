"""validate deployment_architecture type-to-kind constraint

Validates the ``requirements`` type-to-kind CHECK constraint that 0047 added
``NOT VALID``. Runs in its own transaction so the validation scan does not hold
locks during the constraint swap (matches the 0045 / 0046 pattern).

Revision ID: 0048_validate_deployment_architecture_type
Revises: 0047_add_deployment_architecture_type
Create Date: 2026-07-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048_validate_deployment_architecture_type"
down_revision: str | None = "0047_add_deployment_architecture_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIREMENTS_CONSTRAINT = "ck_requirements_submission_value_kind_matches_type"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.execute(
        f"ALTER TABLE requirements VALIDATE CONSTRAINT {_REQUIREMENTS_CONSTRAINT}"
    )


def downgrade() -> None:
    pass
