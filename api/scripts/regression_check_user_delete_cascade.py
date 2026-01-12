"""Tiny regression check: deleting a user cascades dependent rows.

Creates a temporary SQLite database, inserts:
- users
- checklist_progress
- github_submissions

Then deletes the user and asserts dependent rows are gone.

Run:
  /Users/gps/Developer/learn-to-cloud-app/.venv/bin/python api/scripts/regression_check_user_delete_cascade.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import delete, select


def _make_temp_sqlite_url() -> tuple[str, Path]:
    tmp_dir = Path(tempfile.mkdtemp(prefix="ltc-regression-"))
    db_path = tmp_dir / "regression.db"
    return f"sqlite+aiosqlite:///{db_path}", db_path


async def _run() -> None:
    # Allow running from the repo root by ensuring api/ is on sys.path.
    api_dir = Path(__file__).resolve().parents[1]
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))

    database_url, db_path = _make_temp_sqlite_url()

    # Configure the app settings BEFORE importing modules that cache settings/engine.
    os.environ["DATABASE_URL"] = database_url
    os.environ["ENVIRONMENT"] = "development"
    os.environ["RESET_DB_ON_STARTUP"] = "true"

    from shared.config import get_settings
    from shared.database import get_session_maker, init_db, reset_db_state
    from shared.models import ChecklistProgress, GitHubSubmission, SubmissionType, User

    # Clear cached settings/engine to ensure env vars above are used.
    get_settings.cache_clear()
    reset_db_state()

    try:
        await init_db()

        session_maker = get_session_maker()
        async with session_maker() as session:
            user_id = "user_regression"

            session.add(
                User(
                    id=user_id,
                    email="regression@example.com",
                )
            )
            session.add(
                ChecklistProgress(
                    user_id=user_id,
                    checklist_item_id="phase0-check1",
                    phase_id=0,
                    is_completed=True,
                )
            )
            session.add(
                GitHubSubmission(
                    user_id=user_id,
                    requirement_id="phase1-profile-readme",
                    submission_type=SubmissionType.PROFILE_README,
                    phase_id=1,
                    submitted_url="https://github.com/example",
                    is_validated=True,
                )
            )

            await session.commit()

            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()

            remaining_checklist = (
                await session.execute(
                    select(ChecklistProgress).where(ChecklistProgress.user_id == user_id)
                )
            ).scalars().all()
            remaining_submissions = (
                await session.execute(
                    select(GitHubSubmission).where(GitHubSubmission.user_id == user_id)
                )
            ).scalars().all()

            assert remaining_checklist == [], "checklist_progress rows were not cascaded"
            assert remaining_submissions == [], "github_submissions rows were not cascaded"

        print("OK: user deletion cascades checklist_progress and github_submissions")
    finally:
        # Best-effort cleanup of the temporary DB file/dir.
        try:
            db_path.unlink(missing_ok=True)
            db_path.parent.rmdir()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(_run())
