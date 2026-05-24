"""Run the curriculum YAML -> DB sync (issue #463 / Phase B).

Importable CLI entry point for the deploy-time curriculum sync. Must
run in a separate Python process from the Alembic migration runner so
the settings singleton starts fresh as WorkerSettings (Alembic uses
DatabaseSettings; sharing the same process can lock the singleton to
the wrong profile).

Usage (anywhere the ``learn-to-cloud-shared`` wheel is installed)::

    python -m learn_to_cloud_shared.cli.sync_curriculum

Exit codes:
    0  Sync completed cleanly.
    1  Sync aborted (validation error, collision, or other ContentSyncError).
    2  Unexpected exception.

Lives inside the installed package (not in ``scripts/``) so the
production runtime container has it via the wheel -- the runtime image
does not copy the source tree (see ``api/Dockerfile``).

Wired into ``api/scripts/run_migrations.py`` as a subprocess that runs
after ``alembic upgrade head`` in the Container Apps migration job.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import asdict

# Register the minimal settings profile before importing anything that
# touches the shared settings tree. WebSettings (the package default)
# would demand GitHub OAuth secrets in production; not needed here.
from learn_to_cloud_shared.core.config import (
    WorkerSettings,
    configure_settings,
)

configure_settings(WorkerSettings)

from learn_to_cloud_shared.content_sync import (  # noqa: E402
    ContentSyncError,
    sync_curriculum_to_db,
)
from learn_to_cloud_shared.core.database import (  # noqa: E402
    create_engine,
    create_session_maker,
    dispose_engine,
)

logger = logging.getLogger(__name__)


async def _run() -> int:
    engine = create_engine()
    session_maker = create_session_maker(engine)
    try:
        async with session_maker() as session:
            try:
                stats = await sync_curriculum_to_db(session)
                await session.commit()
            except ContentSyncError as exc:
                await session.rollback()
                print(f"Sync aborted: {exc}", file=sys.stderr)
                return 1
    finally:
        await dispose_engine(engine)

    print("Curriculum sync OK")
    for key, value in asdict(stats).items():
        print(f"  {key}: {value}")
    return 0


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("Unexpected error during curriculum sync")
        return 2


if __name__ == "__main__":
    sys.exit(main())
