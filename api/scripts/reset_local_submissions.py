"""Reset local submission records for testing.

Deletes submission rows by requirement ID. Progress is automatically
correct on next page load because it's computed from the submissions table.

Examples:
    uv run python scripts/reset_local_submissions.py
    uv run python scripts/reset_local_submissions.py --dry-run
    uv run python scripts/reset_local_submissions.py --user-id 12345
    uv run python scripts/reset_local_submissions.py \
        --requirement-id devops-implementation
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

from learn_to_cloud.core.database import create_engine

logger = logging.getLogger(__name__)

DEFAULT_REQUIREMENT_IDS = [
    "devops-implementation",
    "journal-api-implementation",
]


async def reset_submissions(
    requirement_ids: list[str],
    user_ids: list[int] | None,
    dry_run: bool,
) -> int:
    """Delete matching submissions.

    Returns number of deleted rows.
    """
    engine = create_engine()
    try:
        async with engine.begin() as conn:
            where_clauses = ["requirement_id = ANY(:requirement_ids)"]
            params: dict[str, object] = {"requirement_ids": requirement_ids}

            if user_ids:
                where_clauses.append("user_id = ANY(:user_ids)")
                params["user_ids"] = user_ids

            where_sql = " AND ".join(where_clauses)

            preview_query = text(
                f"""
                SELECT user_id, requirement_id, phase_id, attempt_number, is_validated
                FROM submissions
                WHERE {where_sql}
                ORDER BY user_id, requirement_id, attempt_number
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
                DELETE FROM submissions
                WHERE {where_sql}
                RETURNING user_id, requirement_id, phase_id
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
        description="Reset local submissions for selected requirement IDs.",
    )
    parser.add_argument(
        "--requirement-id",
        action="append",
        dest="requirement_ids",
        help=(
            "Requirement ID to delete (repeatable). "
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
    requirement_ids = args.requirement_ids or DEFAULT_REQUIREMENT_IDS
    deleted_count = asyncio.run(
        reset_submissions(
            requirement_ids=requirement_ids,
            user_ids=args.user_ids,
            dry_run=args.dry_run,
        )
    )
    logger.info("local.submission_reset.completed", extra={"deleted": deleted_count})


if __name__ == "__main__":
    main()
