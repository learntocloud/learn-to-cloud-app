"""remove dead submission types

Drops the three retired submission types (``journal_api_response``,
``code_analysis``, ``pr_review``) from the only remaining per-type CHECK
constraint, ``ck_requirements_submission_value_kind_matches_type`` on the
``requirements`` table. The ``submissions`` and ``verification_jobs`` tables no
longer have a ``submission_type`` column (dropped in 0029 / 0030), so they need
no change here.

Production was confirmed to have zero ``requirements`` rows (active or
soft-deleted) using these types before this migration was written. The guard
below re-checks that at apply time and refuses to proceed if any offending row
exists, because there is no safe automatic value to migrate a dead curriculum
type to, and we must never silently delete curriculum or learner data.

The tightened constraint is added ``NOT VALID`` here and validated in the
follow-up migration 0042, so the validation scan does not run in the same
transaction as the swap (matches the 0036 / 0037 pattern and keeps squawk
happy).

Revision ID: 0041_remove_dead_submission_types
Revises: 0040_github_username_not_null
Create Date: 2026-06-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0041_remove_dead_submission_types"
down_revision: str | None = "0040_github_username_not_null"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_requirements_submission_value_kind_matches_type"

# New definition: ``pr_review`` removed from the github_url group and the whole
# text group (``journal_api_response`` + ``code_analysis``) dropped, since no
# remaining type uses the ``text`` value kind.
_NEW_CHECK = """
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
"""

# Prior definition, restored on downgrade.
_OLD_CHECK = """
(
    submission_type IN (
        'github_profile',
        'profile_readme',
        'repo_fork',
        'pr_review',
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
        'journal_api_response',
        'code_analysis'
    )
    AND submission_value_kind = 'text'
)
"""

_DEAD_TYPES = "('journal_api_response', 'code_analysis', 'pr_review')"

# Refuse to tighten the constraint if any requirements row still uses a dead
# type. Counts active and soft-deleted rows; raises with a clear message so an
# operator investigates instead of losing data silently.
_GUARD = f"""
DO $$
DECLARE
    offending integer;
BEGIN
    SELECT count(*) INTO offending
    FROM requirements
    WHERE submission_type IN {_DEAD_TYPES};

    IF offending > 0 THEN
        RAISE EXCEPTION
            'Found % requirements row(s) using a retired submission type %. '
            'Resolve these rows manually before removing the types.',
            offending, {_DEAD_TYPES!r};
    END IF;
END $$;
"""


def _replace_constraint(condition: str) -> None:
    op.execute(f"ALTER TABLE requirements DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")
    op.execute(
        f"""
        ALTER TABLE requirements
        ADD CONSTRAINT {_CONSTRAINT}
        CHECK ({condition})
        NOT VALID
        """
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.execute(_GUARD)
    _replace_constraint(_NEW_CHECK)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    _replace_constraint(_OLD_CHECK)
