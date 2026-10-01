"""${message}

Why this change: TODO — describe the motivation in one or two sentences.
Schema effect: TODO — list the tables/columns/indexes affected.
Rollback notes: TODO — call out any data loss or special steps for downgrade.

Revision ID: ${up_revision}
Create Date: ${create_date}
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
