"""Rebuild user phase progress summaries.

Usage:
  uv run --directory api python scripts/rebuild_user_phase_progress.py
  uv run --directory api python scripts/rebuild_user_phase_progress.py --user-id <id>
"""

from __future__ import annotations

import argparse
import asyncio

from core.database import create_engine, create_session_maker, dispose_engine
from services.progress_service import (
    rebuild_all_phase_summaries,
    rebuild_user_phase_summary,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild user phase summaries")
    parser.add_argument("--user-id", help="Rebuild summary for a single user")
    return parser.parse_args()


async def _run(user_id: str | None) -> None:
    engine = create_engine()
    session_maker = create_session_maker(engine)

    try:
        async with session_maker() as session:
            if user_id:
                await rebuild_user_phase_summary(session, user_id)
            else:
                await rebuild_all_phase_summaries(session)
            await session.commit()
    finally:
        await dispose_engine(engine)


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args.user_id))


if __name__ == "__main__":
    main()
