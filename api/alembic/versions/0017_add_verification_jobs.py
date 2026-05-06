"""Add verification job status table.

Revision ID: 0017_add_verification_jobs
Revises: 0016_drop_redundant_indexes
Create Date: 2026-05-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_add_verification_jobs"
down_revision = "0016_drop_redundant_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("requirement_id", sa.String(100), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
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
                "pr_review",
                "ci_status",
                "deployed_api",
                "devops_analysis",
                "security_scanning",
                name="submission_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("submitted_value", sa.Text(), nullable=False),
        sa.Column("extracted_username", sa.String(255), nullable=True),
        sa.Column("cloud_provider", sa.String(16), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "starting",
                "running",
                "succeeded",
                "failed",
                "server_error",
                "cancelled",
                name="verification_job_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("orchestration_instance_id", sa.String(255), nullable=True),
        sa.Column("result_submission_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column("traceparent", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["result_submission_id"], ["submissions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_verification_jobs_user_req_created",
        "verification_jobs",
        ["user_id", "requirement_id", "created_at"],
    )
    op.create_index(
        "ix_verification_jobs_status_updated",
        "verification_jobs",
        ["status", "updated_at"],
    )
    op.create_index(
        "uq_verification_jobs_active_user_requirement",
        "verification_jobs",
        ["user_id", "requirement_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'starting', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_verification_jobs_active_user_requirement",
        table_name="verification_jobs",
    )
    op.drop_index("ix_verification_jobs_status_updated", table_name="verification_jobs")
    op.drop_index(
        "ix_verification_jobs_user_req_created",
        table_name="verification_jobs",
    )
    op.drop_table("verification_jobs")
