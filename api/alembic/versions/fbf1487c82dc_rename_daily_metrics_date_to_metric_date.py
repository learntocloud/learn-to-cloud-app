"""rename_daily_metrics_date_to_metric_date

Revision ID: fbf1487c82dc
Revises: c7d8e9f0a1b2
Create Date: 2026-02-01 03:27:19.216746

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "fbf1487c82dc"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "daily_metrics",
        "date",
        new_column_name="metric_date",
    )


def downgrade() -> None:
    op.alter_column(
        "daily_metrics",
        "metric_date",
        new_column_name="date",
    )
