"""add deployment_architecture submission type (text value kind)

Phase 4 capstone gains an additional ``deployment_architecture`` submission
type whose value is the learner's free-text architecture description (stored in
``text_value``, reusing the ``text`` value kind reintroduced in 0045). This
migration extends only the ``requirements`` type-to-kind CHECK constraint so
``deployment_architecture`` maps to the ``text`` value kind. The typed-value
shape/format constraints and trigger on ``submissions`` / ``verification_jobs``
already handle the ``text`` kind (0045), so they are untouched.

The swapped CHECK is added ``NOT VALID`` here and validated in the follow-up
migration 0048 (matches the 0045 / 0046 pattern, keeping the validation scan
out of this transaction).

Revision ID: 0047_add_deployment_architecture_type
Revises: 0046_validate_reintroduce_text_value_kind
Create Date: 2026-07-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0047_add_deployment_architecture_type"
down_revision: str | None = "0046_validate_reintroduce_text_value_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIREMENTS_CONSTRAINT = "ck_requirements_submission_value_kind_matches_type"

# Type-to-kind check with ``deployment_architecture`` -> ``text`` added.
_REQUIREMENTS_CHECK_WITH_DEPLOYMENT_ARCH = """
(
    submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
        'journal_api_verifier',
        'devops_analysis',
        'security_scanning',
        'ci_status'
    )
    AND submission_value_kind = 'github_url'
)
OR (
    submission_type IN (
        'ctf_token',
        'networking_token',
        'iac_token'
    )
    AND submission_value_kind = 'token'
)
OR (
    submission_type = 'deployed_api'
    AND submission_value_kind = 'deployed_url'
)
OR (
    submission_type IN (
        'career_reflection',
        'deployment_architecture'
    )
    AND submission_value_kind = 'text'
)
"""

# Prior check, restored on downgrade (career_reflection -> text only).
_REQUIREMENTS_CHECK_WITHOUT_DEPLOYMENT_ARCH = """
(
    submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
        'journal_api_verifier',
        'devops_analysis',
        'security_scanning',
        'ci_status'
    )
    AND submission_value_kind = 'github_url'
)
OR (
    submission_type IN (
        'ctf_token',
        'networking_token',
        'iac_token'
    )
    AND submission_value_kind = 'token'
)
OR (
    submission_type = 'deployed_api'
    AND submission_value_kind = 'deployed_url'
)
OR (
    submission_type = 'career_reflection'
    AND submission_value_kind = 'text'
)
"""


def _swap_requirements_check(condition: str) -> None:
    op.execute(
        f"ALTER TABLE requirements DROP CONSTRAINT IF EXISTS {_REQUIREMENTS_CONSTRAINT}"
    )
    op.execute(
        f"""
        ALTER TABLE requirements
        ADD CONSTRAINT {_REQUIREMENTS_CONSTRAINT}
        CHECK ({condition})
        NOT VALID
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    _swap_requirements_check(_REQUIREMENTS_CHECK_WITH_DEPLOYMENT_ARCH)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    _swap_requirements_check(_REQUIREMENTS_CHECK_WITHOUT_DEPLOYMENT_ARCH)
