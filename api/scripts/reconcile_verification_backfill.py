"""Read-only reconciliation report for the verification-attempt backfill.

Run after the expand backfill (migration
``0049_add_verification_attempts_and_step_completions``) and after later
deployments to confirm ``verification_attempts`` /
``learner_step_completions`` agree with the legacy tables. The tool only
runs SELECTs -- it never mutates data.

Usage from the ``api/`` directory::

    uv run python scripts/reconcile_verification_backfill.py

Exit codes:
    0  Fully reconciled (no divergences).
    1  Divergences found (see the printed report).
    2  Could not connect / query error.
"""

from __future__ import annotations

import asyncio
import os
import sys

from learn_to_cloud_shared.verification_reconciliation import (
    format_report,
    run_reconciliation,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _main() -> int:
    database_url = os.environ.get(
        "DATABASE__URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/learn_to_cloud",
    )
    engine = create_async_engine(database_url)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            report = await run_reconciliation(session)
    finally:
        await engine.dispose()

    print(format_report(report))
    return 0 if report.ok else 1


def main() -> int:
    try:
        return asyncio.run(_main())
    except Exception as exc:  # pragma: no cover - operational tool
        print(f"Reconciliation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
