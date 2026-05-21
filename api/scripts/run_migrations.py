"""Run alembic migrations to head and verify the schema actually advanced.

Used both by the Container App Job (`infra/migrations.tf`) and locally. The
post-upgrade verification step exists because the previous migration env
had a substring-based exception swallow that turned real failures into
silent no-ops. This is defense in depth: even if anything ever swallows a
migration error, the final SELECT here will fail the script.
"""

from __future__ import annotations

import logging
import sys

import alembic.command
import alembic.config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from learn_to_cloud._migrations_url import get_sync_database_url

logger = logging.getLogger(__name__)


def main() -> None:
    """Run all alembic migrations, then verify the version row matches head."""
    cfg = alembic.config.Config("alembic.ini")
    alembic.command.upgrade(cfg, "head")

    expected_heads = set(ScriptDirectory.from_config(cfg).get_heads())
    engine = create_engine(get_sync_database_url())
    try:
        with engine.connect() as conn:
            migration_ctx = MigrationContext.configure(conn)
            current_heads = set(migration_ctx.get_current_heads())
    finally:
        engine.dispose()

    if current_heads != expected_heads:
        raise RuntimeError(
            "Migration verification failed: alembic_version "
            f"current={sorted(current_heads) or 'none'} "
            f"expected={sorted(expected_heads) or 'none'}"
        )

    logger.info("migration.verified heads=%s", sorted(current_heads))
    print(f"Schema verified at head(s): {sorted(current_heads)}", file=sys.stderr)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    main()
