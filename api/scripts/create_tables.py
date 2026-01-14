#!/usr/bin/env python3
"""Create database tables from SQLAlchemy models.

Run this once after initial deployment or when setting up a new database.
Note: create_all() only creates missing tables - it won't modify existing ones.
For schema changes on existing tables, you'll need migrations (Alembic).

Usage:
    cd api
    python -m scripts.create_tables
"""

import asyncio
import logging
import sys

# Add parent directory to path so we can import from core
sys.path.insert(0, str(__file__).rsplit("/scripts", 1)[0])

from core.database import Base, get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_tables() -> None:
    """Create all database tables defined in models."""
    # Import models to ensure they're registered with Base.metadata
    import models  # noqa: F401

    engine = get_engine()
    logger.info("Creating database tables...")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Tables created successfully")


if __name__ == "__main__":
    asyncio.run(create_tables())
