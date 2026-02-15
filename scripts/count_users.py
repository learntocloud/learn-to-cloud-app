#!/usr/bin/env python3
"""Count users in the production database."""
import asyncio
import os
import subprocess

import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

_DEFAULT_DB_HOST = "psql-ltc-dev-8v4tyz.postgres.database.azure.com"


async def count_users():
    """Query production database for user count."""
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource-type", "oss-rdbms", "--query", "accessToken", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=True,
    )
    token = result.stdout.strip()

    result = subprocess.run(
        ["az", "ad", "signed-in-user", "show", "--query", "displayName", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=True,
    )
    username = result.stdout.strip()

    db_host = os.environ.get("DATABASE_HOST", _DEFAULT_DB_HOST)
    db_url = f"postgresql+asyncpg://{username}:{token}@{db_host}:5432/learntocloud"

    engine = create_async_engine(db_url, echo=False, connect_args={"ssl": "require"})

    try:
        async with engine.connect() as conn:
            query = sqlalchemy.text("""
                SELECT
                    (SELECT COUNT(*) FROM users) as total_users,
                    (SELECT COUNT(*) FROM users WHERE github_username IS NOT NULL) as users_with_github,
                    (SELECT COUNT(DISTINCT user_id) FROM submissions) as users_with_submissions,
                    (SELECT COUNT(*) FROM submissions) as total_submissions,
                    (SELECT COUNT(*) FROM certificates) as total_certificates,
                    (SELECT COUNT(*) FROM step_progress) as total_steps_completed
            """)
            result = await conn.execute(query)
            row = result.first()

            print(f"Total users: {row[0]}")
            print(f"Users with GitHub: {row[1]}")
            print(f"Users with submissions: {row[2]}")
            print(f"Total submissions: {row[3]}")
            print(f"Total certificates: {row[4]}")
            print(f"Total steps completed: {row[5]}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(count_users())
