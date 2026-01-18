#!/usr/bin/env python3
"""CLI for Learn to Cloud API management tasks.

Usage:
    python -m cli <command>

Commands:
    sync-grading-concepts  Sync grading concepts from content files to database
    migrate                Run database migrations
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_sync_grading_concepts() -> int:
    """Sync grading concepts from content files to database."""
    from scripts.seed_grading_concepts import extract_grading_concepts, seed_database

    logger.info("Extracting grading concepts from content files...")
    concepts = extract_grading_concepts()

    if not concepts:
        logger.warning("No grading concepts found in content files")
        return 1

    logger.info(f"Found {len(concepts)} questions with expected_concepts")
    logger.info("Syncing to database...")

    asyncio.run(seed_database(concepts))

    logger.info("Grading concepts sync complete")
    return 0


def cmd_migrate() -> int:
    """Run database migrations."""
    from alembic import command
    from scripts.migrate import _get_alembic_config

    logger.info("Running database migrations...")
    cfg = _get_alembic_config()
    command.upgrade(cfg, "head")
    logger.info("Migrations complete")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Learn to Cloud API CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser(
        "sync-grading-concepts",
        help="Sync grading concepts from content files to database",
    )
    subparsers.add_parser(
        "migrate",
        help="Run database migrations",
    )

    args = parser.parse_args()

    if args.command == "sync-grading-concepts":
        return cmd_sync_grading_concepts()
    elif args.command == "migrate":
        return cmd_migrate()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
