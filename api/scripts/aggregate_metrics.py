#!/usr/bin/env python
"""Aggregate daily metrics - run as scheduled job.

Usage:
    # Aggregate yesterday (default)
    uv run python scripts/aggregate_metrics.py

    # Aggregate specific date
    uv run python scripts/aggregate_metrics.py --date 2026-01-29

    # Backfill a range
    uv run python scripts/aggregate_metrics.py --backfill --start 2025-01-01 --end 2026-01-29

Environment:
    Requires DATABASE_URL environment variable.
    Load from .env: source .env && uv run python scripts/aggregate_metrics.py
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Add api directory to path for imports
api_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(api_dir))

from core.database import create_engine, create_session_maker, dispose_engine
from core.logger import configure_logging, get_logger
from services.metrics_service import aggregate_daily_metrics, backfill_metrics

configure_logging()
logger = get_logger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Aggregate daily metrics")
    parser.add_argument(
        "--date",
        type=str,
        help="Date to aggregate (YYYY-MM-DD). Defaults to yesterday.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill mode: aggregate a date range",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date for backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date for backfill (YYYY-MM-DD). Defaults to yesterday.",
    )
    args = parser.parse_args()

    engine = create_engine()
    session_maker = create_session_maker(engine)

    try:
        async with session_maker() as db:
            if args.backfill:
                if not args.start:
                    logger.error("--start is required for backfill mode")
                    sys.exit(1)

                start_date = date.fromisoformat(args.start)
                end_date = (
                    date.fromisoformat(args.end)
                    if args.end
                    else datetime.now(UTC).date() - timedelta(days=1)
                )

                logger.info(
                    "backfill.starting",
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )

                days = await backfill_metrics(db, start_date, end_date)
                logger.info("backfill.complete", days_aggregated=days)

            else:
                if args.date:
                    target_date = date.fromisoformat(args.date)
                else:
                    target_date = datetime.now(UTC).date() - timedelta(days=1)

                logger.info("aggregate.starting", date=target_date.isoformat())

                await aggregate_daily_metrics(db, target_date)
                await db.commit()

                logger.info("aggregate.complete", date=target_date.isoformat())

    finally:
        await dispose_engine(engine)


if __name__ == "__main__":
    asyncio.run(main())
