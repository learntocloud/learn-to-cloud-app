"""Drop legacy verification_jobs status / lifecycle columns.

Final contract step of the verification-jobs slim-down. PR4 removed all
application-code references to these columns; this revision drops them
from the schema. Safe to run only after the PR4 ACA + Verification
Functions rollouts have fully drained — older pods would crash on
``SELECT verification_jobs.*`` once any of these columns disappear.

Columns dropped:
* ``status`` (VARCHAR with CHECK constraint; ``native_enum=False`` so
  no native Postgres ENUM type to drop).
* ``orchestration_instance_id``
* ``error_code``
* ``error_message``
* ``started_at``
* ``completed_at``

The PR4 migration's ``status DEFAULT 'queued'`` goes with the column.

Revision ID: 0022_drop_verification_job_legacy_columns
Revises: 0021_decouple_verification_jobs_from_status
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_drop_verification_job_legacy_columns"
down_revision = "0021_decouple_verification_jobs_from_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("verification_jobs", "status")
    op.drop_column("verification_jobs", "orchestration_instance_id")
    op.drop_column("verification_jobs", "error_code")
    op.drop_column("verification_jobs", "error_message")
    op.drop_column("verification_jobs", "started_at")
    op.drop_column("verification_jobs", "completed_at")


def downgrade() -> None:
    op.add_column(
        "verification_jobs",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "verification_jobs",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "verification_jobs",
        sa.Column(
            "error_message",
            sa.String(length=1024),
            nullable=True,
        ),
    )
    op.add_column(
        "verification_jobs",
        sa.Column(
            "error_code",
            sa.String(length=100),
            nullable=True,
        ),
    )
    op.add_column(
        "verification_jobs",
        sa.Column(
            "orchestration_instance_id",
            sa.String(length=255),
            nullable=True,
        ),
    )
    # Re-create ``status`` as nullable + DEFAULT so the downgrade does
    # not require a backfill. The original NOT NULL constraint can only
    # be safely re-applied by running PR4's data migration; if you need
    # the strict original schema, restore from a pre-PR5 backup instead.
    op.add_column(
        "verification_jobs",
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
            ),
            nullable=True,
            server_default="queued",
        ),
    )
