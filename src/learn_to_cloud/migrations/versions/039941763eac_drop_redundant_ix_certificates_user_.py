"""drop redundant ix_certificates_user index

Revision ID: 039941763eac
Revises: 0012_remove_iac_token_add_pr_review
Create Date: 2026-02-15 15:00:22.411537

"""

from __future__ import annotations

from alembic import op

revision = "039941763eac"
down_revision = "0012_remove_iac_token_add_pr_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("certificates", schema=None) as batch_op:
        batch_op.drop_index("ix_certificates_user")


def downgrade() -> None:
    with op.batch_alter_table("certificates", schema=None) as batch_op:
        batch_op.create_index("ix_certificates_user", ["user_id"], unique=False)
