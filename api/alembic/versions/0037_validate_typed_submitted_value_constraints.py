"""validate typed submitted value constraints

Revision ID: 0037_validate_typed_submitted_value_constraints
Revises: 0036_typed_submitted_values
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037_validate_typed_submitted_value_constraints"
down_revision: str | None = "0036_typed_submitted_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPED_VALUE_FORMAT_CHECK = """
(
    github_url IS NULL
    OR length(btrim(github_url)) > 0
)
AND (
    deployed_url IS NULL
    OR length(btrim(deployed_url)) > 0
)
AND (
    token_value IS NULL
    OR length(btrim(token_value)) > 0
)
AND (
    text_value IS NULL
    OR length(btrim(text_value)) > 0
)
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")

    _replace_typed_value_format_constraint("submissions", "ck_submissions")
    _replace_typed_value_format_constraint("verification_jobs", "ck_verification_jobs")

    for table, constraints in {
        "requirements": ("ck_requirements_submission_value_kind_matches_type",),
        "submissions": (
            "ck_submissions_typed_value_shape",
            "ck_submissions_typed_value_format",
            "fk_submissions_requirement_value_kind",
        ),
        "verification_jobs": (
            "ck_verification_jobs_typed_value_shape",
            "ck_verification_jobs_typed_value_format",
            "fk_verification_jobs_requirement_value_kind",
        ),
    }.items():
        for constraint in constraints:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")


def downgrade() -> None:
    pass


def _replace_typed_value_format_constraint(table: str, prefix: str) -> None:
    constraint = f"{prefix}_typed_value_format"
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
    op.execute(
        f"""
        ALTER TABLE {table}
        ADD CONSTRAINT {constraint}
        CHECK ({_TYPED_VALUE_FORMAT_CHECK})
        NOT VALID
        """
    )
