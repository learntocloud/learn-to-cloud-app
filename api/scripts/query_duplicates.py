"""Query for duplicate github usernames and show user details."""

import asyncio

from sqlalchemy import text

from core.database import get_engine


async def main():
    """Find and display duplicate github usernames."""
    engine = get_engine()
    async with engine.connect() as conn:
        # Find duplicates
        result = await conn.execute(
            text("""
                SELECT github_username, COUNT(*) as cnt
                FROM users
                WHERE github_username IS NOT NULL
                GROUP BY github_username
                HAVING COUNT(*) > 1
            """)
        )
        duplicates = list(result.fetchall())

        if not duplicates:
            print("No duplicates found!")
            return

        print(f"Found {len(duplicates)} github_username(s) with duplicates:")
        for username, count in duplicates:
            print(f"\n=== {username} ({count} users) ===")
            # Get details for each duplicate
            details = await conn.execute(
                text("""
                    SELECT id, email, first_name, created_at,
                           (SELECT COUNT(*) FROM submissions
                            WHERE user_id = u.id) as submission_count,
                           (SELECT COUNT(*) FROM user_activities
                            WHERE user_id = u.id) as activity_count
                    FROM users u
                    WHERE github_username = :username
                    ORDER BY created_at
                """),
                {"username": username},
            )
            for row in details:
                print(
                    f"  ID: {row[0][:20]}... | Email: {row[1]} | "
                    f"Name: {row[2]} | Created: {row[3]} | "
                    f"Submissions: {row[4]} | Activities: {row[5]}"
                )


if __name__ == "__main__":
    asyncio.run(main())
