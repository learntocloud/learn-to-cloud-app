"""Drop certificates table.

The certificate-of-completion feature has been removed from the
application. This migration drops the certificates table and its
unique constraint.

Revision ID: 0014_drop_certificates_table
Revises: 0013_drop_completed_steps_column
Create Date: 2026-02-16
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_drop_certificates_table"
down_revision = "0013_drop_completed_steps_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("certificates")


def downgrade() -> None:
    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("verification_code", sa.String(64), nullable=False, unique=True),
        sa.Column("recipient_name", sa.String(255), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phases_completed", sa.Integer(), nullable=False),
        sa.Column("total_phases", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_certificate"),
    )
