"""Integration tests for repositories/submission_repository.py.

Uses real PostgreSQL database with transaction rollback for isolation.
"""

from datetime import UTC, datetime

import pytest

from models import Submission, SubmissionType, User
from repositories.submission_repository import SubmissionRepository


@pytest.mark.asyncio
class TestSubmissionRepositoryIntegration:
    """Integration tests for SubmissionRepository."""

    async def _create_user(self, db_session, user_id: str = "test-user"):
        """Helper to create a user for FK constraint."""
        user = User(id=user_id, email=f"{user_id}@example.com")
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_get_by_user_and_requirement_returns_submission(self, db_session):
        """get_by_user_and_requirement returns existing submission."""
        await self._create_user(db_session)
        submission = Submission(
            user_id="test-user",
            requirement_id="phase1-req1",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo",
        )
        db_session.add(submission)
        await db_session.flush()

        repo = SubmissionRepository(db_session)
        result = await repo.get_by_user_and_requirement("test-user", "phase1-req1")

        assert result is not None
        assert result.user_id == "test-user"
        assert result.requirement_id == "phase1-req1"

    async def test_get_by_user_and_requirement_returns_none_if_not_found(
        self, db_session
    ):
        """get_by_user_and_requirement returns None for missing submission."""
        repo = SubmissionRepository(db_session)
        result = await repo.get_by_user_and_requirement("nonexistent", "nonexistent")
        assert result is None

    async def test_get_by_user_and_phase_returns_submissions(self, db_session):
        """get_by_user_and_phase returns all submissions for a phase."""
        await self._create_user(db_session)
        sub1 = Submission(
            user_id="test-user",
            requirement_id="phase1-req1",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo1",
        )
        sub2 = Submission(
            user_id="test-user",
            requirement_id="phase1-req2",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo2",
        )
        sub3 = Submission(
            user_id="test-user",
            requirement_id="phase2-req1",
            phase_id=2,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo3",
        )
        db_session.add_all([sub1, sub2, sub3])
        await db_session.flush()

        repo = SubmissionRepository(db_session)
        results = await repo.get_by_user_and_phase("test-user", 1)

        assert len(results) == 2
        requirement_ids = {s.requirement_id for s in results}
        assert requirement_ids == {"phase1-req1", "phase1-req2"}

    async def test_get_by_user_and_phase_returns_empty_list(self, db_session):
        """get_by_user_and_phase returns empty list for no submissions."""
        repo = SubmissionRepository(db_session)
        results = await repo.get_by_user_and_phase("nonexistent", 1)
        assert results == []

    async def test_get_validated_by_user_returns_only_validated(self, db_session):
        """get_validated_by_user returns only validated submissions."""
        await self._create_user(db_session)
        validated = Submission(
            user_id="test-user",
            requirement_id="phase1-req1",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo1",
            is_validated=True,
            validated_at=datetime.now(UTC),
        )
        not_validated = Submission(
            user_id="test-user",
            requirement_id="phase1-req2",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo2",
            is_validated=False,
        )
        db_session.add_all([validated, not_validated])
        await db_session.flush()

        repo = SubmissionRepository(db_session)
        results = await repo.get_validated_by_user("test-user")

        assert len(results) == 1
        assert results[0].requirement_id == "phase1-req1"
        assert results[0].is_validated is True

    async def test_get_validated_by_user_returns_empty_for_no_validated(
        self, db_session
    ):
        """get_validated_by_user returns empty list if none validated."""
        await self._create_user(db_session)
        not_validated = Submission(
            user_id="test-user",
            requirement_id="phase1-req1",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo1",
            is_validated=False,
        )
        db_session.add(not_validated)
        await db_session.flush()

        repo = SubmissionRepository(db_session)
        results = await repo.get_validated_by_user("test-user")

        assert results == []

    async def test_upsert_creates_new_submission(self, db_session):
        """upsert creates submission when it doesn't exist."""
        await self._create_user(db_session)
        await db_session.commit()  # Commit user to avoid FK issues

        repo = SubmissionRepository(db_session)
        result = await repo.upsert(
            user_id="test-user",
            requirement_id="phase1-req1",
            submission_type=SubmissionType.REPO_URL,
            phase_id=1,
            submitted_value="https://github.com/user/repo",
            extracted_username="user",
            is_validated=True,
        )

        assert result.user_id == "test-user"
        assert result.requirement_id == "phase1-req1"
        assert result.is_validated is True
        assert result.validated_at is not None
        assert result.extracted_username == "user"

    async def test_upsert_updates_existing_submission(self, db_session):
        """upsert updates submission when it exists."""
        await self._create_user(db_session)
        existing = Submission(
            user_id="test-user",
            requirement_id="phase1-req1",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/old-repo",
            is_validated=False,
        )
        db_session.add(existing)
        await db_session.commit()
        db_session.expire_all()

        repo = SubmissionRepository(db_session)
        await repo.upsert(
            user_id="test-user",
            requirement_id="phase1-req1",
            submission_type=SubmissionType.REPO_URL,
            phase_id=1,
            submitted_value="https://github.com/user/new-repo",
            extracted_username="user",
            is_validated=True,
        )

        db_session.expire_all()
        # Fetch from DB to verify update
        from sqlalchemy import select

        stmt = select(Submission).where(
            Submission.user_id == "test-user",
            Submission.requirement_id == "phase1-req1",
        )
        res = await db_session.execute(stmt)
        fetched = res.scalar_one()

        assert fetched.submitted_value == "https://github.com/user/new-repo"
        assert fetched.is_validated is True
        assert fetched.extracted_username == "user"

    async def test_validated_submissions_ordered_by_phase_and_time(self, db_session):
        """get_validated_by_user orders by phase then validated_at."""
        await self._create_user(db_session)
        now = datetime.now(UTC)

        sub_phase2 = Submission(
            user_id="test-user",
            requirement_id="phase2-req1",
            phase_id=2,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo2",
            is_validated=True,
            validated_at=now,
        )
        sub_phase1 = Submission(
            user_id="test-user",
            requirement_id="phase1-req1",
            phase_id=1,
            submission_type=SubmissionType.REPO_URL,
            submitted_value="https://github.com/user/repo1",
            is_validated=True,
            validated_at=now,
        )
        db_session.add_all([sub_phase2, sub_phase1])
        await db_session.flush()

        repo = SubmissionRepository(db_session)
        results = await repo.get_validated_by_user("test-user")

        assert len(results) == 2
        # Phase 1 should come before phase 2
        assert results[0].phase_id == 1
        assert results[1].phase_id == 2
