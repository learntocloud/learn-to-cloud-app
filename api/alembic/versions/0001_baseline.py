"""fresh baseline for htmx migration

Revision ID: 0001_baseline
Revises:
Create Date: 2026-02-06

Fresh schema with GitHub numeric user IDs as primary key.
Replaces all previous Clerk-based migrations.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table - GitHub numeric user ID as PK
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("github_username", sa.String(255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_username", name="uq_users_github_username"),
    )

    # Submissions table
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("requirement_id", sa.String(100), nullable=False),
        sa.Column(
            "submission_type",
            sa.Enum(
                "github_profile",
                "profile_readme",
                "repo_fork",
                "ctf_token",
                "networking_token",
                "journal_api_response",
                "code_analysis",
                "deployed_api",
                "devops_analysis",
                "security_scanning",
                name="submission_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column("submitted_value", sa.Text(), nullable=False),
        sa.Column("extracted_username", sa.String(255), nullable=True),
        sa.Column("is_validated", sa.Boolean(), default=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_completed", sa.Boolean(), default=False),
        sa.Column("feedback_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "requirement_id", name="uq_user_requirement"),
    )
    op.create_index("ix_submissions_user_phase", "submissions", ["user_id", "phase_id"])
    op.create_index(
        "ix_submissions_user_phase_validated",
        "submissions",
        ["user_id", "phase_id"],
        postgresql_where=sa.text("is_validated"),
    )

    # Step Progress table
    op.create_table(
        "step_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.String(100), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "topic_id", "step_order", name="uq_user_topic_step"
        ),
    )
    op.create_index(
        "ix_step_progress_user_topic", "step_progress", ["user_id", "topic_id"]
    )
    op.create_index(
        "ix_step_progress_user_phase", "step_progress", ["user_id", "phase_id"]
    )

    # Certificates table
    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("certificate_type", sa.String(50), nullable=False),
        sa.Column("verification_code", sa.String(64), nullable=False, unique=True),
        sa.Column("recipient_name", sa.String(255), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phases_completed", sa.Integer(), nullable=False),
        sa.Column("total_phases", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "certificate_type", name="uq_user_certificate"),
    )
    op.create_index("ix_certificates_user", "certificates", ["user_id"])

    # User Activities table
    op.create_table(
        "user_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "activity_type",
            sa.Enum(
                "step_complete",
                "topic_complete",
                "hands_on_validated",
                "phase_complete",
                "certificate_earned",
                name="activity_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_user_activities_user_date",
        "user_activities",
        ["user_id", "activity_date"],
    )
    op.create_index(
        "ix_user_activities_user_type",
        "user_activities",
        ["user_id", "activity_type"],
    )


def downgrade() -> None:
    op.drop_table("user_activities")
    op.drop_table("certificates")
    op.drop_table("step_progress")
    op.drop_table("submissions")
    op.drop_table("users")
