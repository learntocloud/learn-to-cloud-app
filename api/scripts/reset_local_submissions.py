"""Reset local verification attempts for testing.

Deletes ``verification_attempts`` rows for the given requirement slugs. Progress
is computed from those attempts, so removing them restores the pre-submission
state on the next page load.

Slugs are resolved to ``requirement_uuid`` through the curriculum artifact
rather than the database: attempts store the requirement by UUID, and the
embedded ``requirement_snapshot`` is absent on reconstructed rows, so matching
on the snapshot alone would silently miss them.

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
import sys
from urllib.parse import urlsplit
from uuid import UUID

from learn_to_cloud_shared.core.config import get_migration_settings
from learn_to_cloud_shared.core.database import create_engine
from learn_to_cloud_shared.requirements import get_requirement_by_slug
from sqlalchemy import bindparam, text

logger = logging.getLogger(__name__)

DEFAULT_REQUIREMENT_SLUGS = [
    "devops-implementation",
    "journal-api-implementation",
]


def resolve_requirement_uuids(requirement_slugs: list[str]) -> dict[str, UUID]:
    """Map each slug to its requirement UUID, raising on unknown slugs."""
    resolved: dict[str, UUID] = {}
    unknown: list[str] = []
    for slug in requirement_slugs:
        requirement = get_requirement_by_slug(slug)
        if requirement is None:
            unknown.append(slug)
        else:
            resolved[slug] = requirement.uuid

    if unknown:
        raise SystemExit(
            f"Unknown requirement slug(s): {', '.join(sorted(unknown))}. "
            "Check the slugs in the curriculum artifact."
        )
    return resolved


async def reset_attempts(
    requirement_slugs: list[str],
    user_ids: list[int] | None,
    dry_run: bool,
) -> int:
    """Delete matching verification attempts, returning the number removed."""
    uuid_by_slug = resolve_requirement_uuids(requirement_slugs)
    slug_by_uuid = {value: key for key, value in uuid_by_slug.items()}

    where = "requirement_uuid IN :requirement_uuids"
    params: dict[str, object] = {"requirement_uuids": list(uuid_by_slug.values())}
    bind_params = [bindparam("requirement_uuids", expanding=True)]
    if user_ids:
        where += " AND user_id IN :user_ids"
        params["user_ids"] = user_ids
        bind_params.append(bindparam("user_ids", expanding=True))

    engine = create_engine(get_migration_settings().database)
    try:
        async with engine.begin() as conn:
            preview_query = text(
                f"""
                SELECT user_id, requirement_uuid, outcome
                FROM verification_attempts
                WHERE {where}
                ORDER BY user_id, created_at
                """
            ).bindparams(*bind_params)
            rows = (await conn.execute(preview_query, params)).fetchall()

            if not rows:
                print("No matching verification attempts found.")
                return 0

            print(f"Matches found: {len(rows)} attempt(s)")
            for row in rows:
                slug = slug_by_uuid.get(row.requirement_uuid, str(row.requirement_uuid))
                print(f"  user_id={row.user_id} {slug} outcome={row.outcome or 'open'}")

            if dry_run:
                print("Dry run enabled: no changes applied.")
                return 0

            delete_query = text(
                f"""
                DELETE FROM verification_attempts
                WHERE {where}
                RETURNING user_id
                """
            ).bindparams(*bind_params)
            deleted = (await conn.execute(delete_query, params)).fetchall()
            print(f"Deleted {len(deleted)} verification attempt(s).")
            return len(deleted)
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset local verification attempts for selected requirements.",
    )
    parser.add_argument(
        "--requirement-slug",
        action="append",
        dest="requirement_slugs",
        help=(
            "Requirement slug to reset (repeatable). "
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


def _is_local_database(url: str) -> bool:
    """True when the URL points at a development database host."""
    host = urlsplit(url).hostname or ""
    return host in {"localhost", "127.0.0.1", "::1", "db", "postgres"}


def main() -> None:
    args = parse_args()
    settings = get_migration_settings()
    if settings.database.use_azure_postgres or not _is_local_database(
        settings.database.url
    ):
        print(
            "Refusing to run: the configured database is not a local development "
            "host. This script is for local development only.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    deleted_count = asyncio.run(
        reset_attempts(
            requirement_slugs=args.requirement_slugs or DEFAULT_REQUIREMENT_SLUGS,
            user_ids=args.user_ids,
            dry_run=args.dry_run,
        )
    )
    logger.info("local.attempt_reset.completed", extra={"deleted": deleted_count})


if __name__ == "__main__":
    main()
