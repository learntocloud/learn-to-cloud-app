#!/usr/bin/env python3
"""Seed grading_concepts table from grading JSON files.

This script loads expected_concepts from *.grading.json files
and populates the grading_concepts table. Grading files use a minimal
format: {"question_id": ["concept1", "concept2", ...]}.

Usage:
    python -m scripts.seed_grading_concepts

Environment:
    DATABASE_URL - PostgreSQL connection string (required)
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Grading directory (separate from public content)
GRADING_DIR = Path(__file__).parent.parent.parent / "content" / "grading"


def extract_grading_concepts() -> list[dict]:
    """Load all question_id -> expected_concepts mappings from grading files."""
    concepts = []

    for phase_dir in sorted(GRADING_DIR.iterdir()):
        if not phase_dir.is_dir() or phase_dir.name.startswith("."):
            continue

        for grading_file in sorted(phase_dir.glob("*.grading.json")):
            try:
                with open(grading_file, encoding="utf-8") as f:
                    data = json.load(f)

                # Grading files have format: {"question_id": ["concept1", "concept2", ...]}
                for question_id, expected in data.items():
                    if question_id and expected:
                        concepts.append(
                            {
                                "question_id": question_id,
                                "expected_concepts": expected,
                            }
                        )
                        count = len(expected)
                        logger.info(f"Loaded: {question_id} ({count} concepts)")

            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error reading {grading_file}: {e}")
                continue

    return concepts


async def seed_database(concepts: list[dict]) -> None:
    """Upsert grading concepts into the database."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Upsert each concept (insert or update if exists)
        inserted = 0
        updated = 0
        for concept in concepts:
            result = await session.execute(
                text("""
                    INSERT INTO grading_concepts (
                        question_id, expected_concepts, created_at, updated_at
                    )
                    VALUES (:question_id, :expected_concepts, NOW(), NOW())
                    ON CONFLICT (question_id) DO UPDATE SET
                        expected_concepts = EXCLUDED.expected_concepts,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                """),
                {
                    "question_id": concept["question_id"],
                    "expected_concepts": json.dumps(concept["expected_concepts"]),
                },
            )
            row = result.fetchone()
            if row and row[0]:
                inserted += 1
            else:
                updated += 1

        await session.commit()
        logger.info(f"Grading concepts: {inserted} inserted, {updated} updated")

    await engine.dispose()


def main() -> None:
    """Main entry point."""
    logger.info(f"Loading grading concepts from {GRADING_DIR}")
    concepts = extract_grading_concepts()
    logger.info(f"Found {len(concepts)} questions with expected_concepts")

    if not concepts:
        logger.warning("No concepts found. Check content directory.")
        return

    logger.info("Seeding database...")
    asyncio.run(seed_database(concepts))
    logger.info("Done!")


if __name__ == "__main__":
    main()
