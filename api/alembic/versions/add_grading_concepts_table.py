"""add grading_concepts table

Revision ID: a1b2c3d4e5f6
Revises: 86361256be54
Create Date: 2026-01-18 12:00:00.000000

"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "86361256be54"
branch_labels = None
depends_on = None


def _extract_grading_concepts() -> list[dict]:
    """Extract all question_id -> expected_concepts mappings from content."""
    # Content directory relative to this migration file
    content_dir = Path(__file__).parent.parent.parent.parent / "content" / "phases"
    concepts = []

    if not content_dir.exists():
        # Fallback for CI/CD where content might be at different location
        content_dir = Path("/app/content/phases")
        if not content_dir.exists():
            return concepts

    for phase_dir in sorted(content_dir.iterdir()):
        if not phase_dir.is_dir() or phase_dir.name.startswith("."):
            continue

        for topic_file in sorted(phase_dir.glob("*.json")):
            if topic_file.name == "index.json":
                continue

            try:
                with open(topic_file, encoding="utf-8") as f:
                    data = json.load(f)

                for question in data.get("questions", []):
                    question_id = question.get("id")
                    expected = question.get("expected_concepts", [])

                    if question_id and expected:
                        concepts.append(
                            {
                                "question_id": question_id,
                                "expected_concepts": expected,
                            }
                        )

            except (json.JSONDecodeError, KeyError):
                continue

    return concepts


def upgrade() -> None:
    """Create grading_concepts table and seed with data from content files."""
    op.create_table(
        "grading_concepts",
        sa.Column("question_id", sa.String(length=100), nullable=False),
        sa.Column("expected_concepts", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("question_id"),
    )
    with op.batch_alter_table("grading_concepts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_grading_concepts_question_id"),
            ["question_id"],
            unique=False,
        )

    # Seed data from content files
    concepts = _extract_grading_concepts()
    if concepts:
        now = datetime.now(UTC)
        grading_concepts = sa.table(
            "grading_concepts",
            sa.column("question_id", sa.String),
            sa.column("expected_concepts", JSONB),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            grading_concepts,
            [
                {
                    "question_id": c["question_id"],
                    "expected_concepts": c["expected_concepts"],
                    "created_at": now,
                    "updated_at": now,
                }
                for c in concepts
            ],
        )


def downgrade() -> None:
    """Remove grading_concepts table."""
    with op.batch_alter_table("grading_concepts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_grading_concepts_question_id"))
    op.drop_table("grading_concepts")
