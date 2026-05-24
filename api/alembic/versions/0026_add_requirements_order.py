"""add requirements order

Why this change: Phase B (#463) created the ``requirements`` table but
omitted an ``order`` column -- an oversight surfaced when planning
Phase C (#464) parity tests. Phases, topics, steps, and
learning_objectives all carry ``order``; requirements should too, so
the DB faithfully represents the slug-list order from
``_phase.yaml``'s ``requirements:``.

Schema effect: Adds ``requirements.order BIGINT NOT NULL`` with a
``server_default = '0'`` so existing rows are backfilled in place. The
deploy-time sync (``scripts/sync_curriculum.py``) overwrites these
values with the real position-based order on its next run, so the
default never sticks.

Rollback notes: Pure additive column. Downgrade drops it. Safe.

Revision ID: 0026_add_requirements_order
Create Date: 2026-05-24 18:32:03.167995
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026_add_requirements_order"
down_revision = "0025_add_curriculum_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")

    op.add_column(
        "requirements",
        sa.Column(
            "order",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("requirements", "order")
