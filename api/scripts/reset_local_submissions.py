"""Reset local submission records for testing.

Deletes submission rows by requirement slug. Progress is automatically
correct on next page load because it's computed from the submissions table.

Submissions reference a requirement by ``requirement_uuid`` (FK to
``requirements.uuid``); the human-friendly slug lives on the requirements
table, so we join through it to match the slugs passed on the command line.

Examples:
    uv run python scripts/reset_local_submissions.py
    uv run python scripts/reset_local_submissions.py --dry-run
    uv run python scripts/reset_local_submissions.py --user-id 12345
    uv run python scripts/reset_local_submissions.py \
        --requirement-slug devops-implementation
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from learn_to_cloud_shared.core.config import get_web_settings
from learn_to_cloud_shared.core.database import create_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

DEFAULT_REQUIREMENT_SLUGS = [
    "devops-implementation",
    "journal-api-implementation",
]


async def reset_submissions(
    requirement_slugs: list[str],
    user_ids: list[int] | None,
    dry_run: bool,
) -> int:
    """Delete matching submissions.

    Returns number of deleted rows.
    """
    engine = create_engine(get_web_settings().database)
    try:
        async with engine.begin() as conn:
            params: dict[str, object] = {"requirement_slugs": requirement_slugs}
            user_filter = ""
            if user_ids:
                user_filter = " AND s.user_id = ANY(:user_ids)"
                params["user_ids"] = user_ids

            preview_query = text(
                f"""
                SELECT s.user_id, r.slug AS requirement_slug, s.is_validated
                FROM submissions s
                JOIN requirements r ON r.uuid = s.requirement_uuid
                WHERE r.slug = ANY(:requirement_slugs){user_filter}
                ORDER BY s.user_id, r.slug
                """
            )
            preview_result = await conn.execute(preview_query, params)
            rows = preview_result.fetchall()

            if not rows:
                print("No matching submissions found.")
                return 0

            affected_user_ids = sorted({row.user_id for row in rows})

            print(
                "Matches found: "
                f"{len(rows)} row(s) across user_id(s)={affected_user_ids}"
            )

            if dry_run:
                print("Dry run enabled: no changes applied.")
                return 0

            delete_query = text(
                f"""
                DELETE FROM submissions s
                USING requirements r
                WHERE r.uuid = s.requirement_uuid
                  AND r.slug = ANY(:requirement_slugs){user_filter}
                RETURNING s.user_id, r.slug AS requirement_slug
                """
            )
            delete_result = await conn.execute(delete_query, params)
            deleted_rows = delete_result.fetchall()
            print(f"Deleted {len(deleted_rows)} submission row(s).")

            return len(deleted_rows)
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset local submissions for selected requirement slugs.",
    )
    parser.add_argument(
        "--requirement-slug",
        action="append",
        dest="requirement_slugs",
        help=(
            "Requirement slug to delete (repeatable). "
            "Defaults to devops-implementation and journal-api-implementation."
        ),
    )
    parser.add_argument(
        "--user-id",
        action="append",
        type=int,
        dest="user_ids",
        help="Restrict deletion to one or more user IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without applying changes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requirement_slugs = args.requirement_slugs or DEFAULT_REQUIREMENT_SLUGS
    deleted_count = asyncio.run(
        reset_submissions(
            requirement_slugs=requirement_slugs,
            user_ids=args.user_ids,
            dry_run=args.dry_run,
        )
    )
    logger.info("local.submission_reset.completed", extra={"deleted": deleted_count})


if __name__ == "__main__":
    main()
