"""drop certificate_type column

Revision ID: 0003_drop_certificate_type
Revises: 0002_drop_activities
Create Date: 2026-02-07

Remove the certificate_type column from certificates table.
Only one certificate type (full_completion) exists, making the column redundant.
The unique constraint changes from (user_id, certificate_type) to just (user_id).
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_drop_certificate_type"
down_revision = "0002_drop_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_user_certificate", "certificates", type_="unique")
    op.drop_column("certificates", "certificate_type")
    op.create_unique_constraint("uq_user_certificate", "certificates", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_user_certificate", "certificates", type_="unique")
    op.add_column(
        "certificates",
        sa.Column(
            "certificate_type",
            sa.String(50),
            nullable=False,
            server_default="full_completion",
        ),
    )
    op.create_unique_constraint(
        "uq_user_certificate", "certificates", ["user_id", "certificate_type"]
    )
