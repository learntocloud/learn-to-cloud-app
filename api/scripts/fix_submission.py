#!/usr/bin/env python3
"""Fix the failed journal-starter-fork submission.

Usage:
    cd api
    python -m scripts.fix_submission
"""
import asyncio
import sys

# Add parent directory to path so we can import from core
sys.path.insert(0, str(__file__).rsplit("/scripts", 1)[0])

from sqlalchemy import text

from core.database import get_session_maker


async def fix_submission():
    """Fix the submission that failed due to missing https:// prefix."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        # Update the submission
        result = await session.execute(
            text("""
                UPDATE submissions 
                SET is_validated = true, 
                    extracted_username = 'madebygps',
                    submitted_value = 'https://github.com/madebygps/journal-starter'
                WHERE requirement_id = 'phase2-journal-starter-fork' 
                AND is_validated = false
            """)
        )
        await session.commit()
        print(f"Updated {result.rowcount} submission(s)")


if __name__ == "__main__":
    asyncio.run(fix_submission())
