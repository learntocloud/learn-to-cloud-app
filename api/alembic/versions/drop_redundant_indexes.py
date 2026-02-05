"""drop redundant indexes

Three indexes duplicate unique constraints that already create implicit indexes:
- ix_users_github_username (duplicated by uq_users_github_username)
- ix_certificates_verification (duplicated by certificates_verification_code_key)
- ix_step_progress_lookup (duplicated by uq_user_topic_step, same 3 columns)

Dropping these reduces write overhead with no impact on read performance.

Revision ID: drop_redundant_indexes
Revises: drop_user_phase_progress
Create Date: 2026-02-05

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "drop_redundant_indexes"
down_revision = "drop_user_phase_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_github_username", table_name="users")
    op.drop_index("ix_certificates_verification", table_name="certificates")
    op.drop_index("ix_step_progress_lookup", table_name="step_progress")


def downgrade() -> None:
    op.create_index(
        "ix_step_progress_lookup",
        "step_progress",
        ["user_id", "topic_id", "step_order"],
    )
    op.create_index(
        "ix_certificates_verification",
        "certificates",
        ["verification_code"],
    )
    op.create_index(
        "ix_users_github_username",
        "users",
        ["github_username"],
    )
