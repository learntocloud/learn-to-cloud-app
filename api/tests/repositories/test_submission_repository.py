"""Tests for SubmissionRepository.

Tests database operations for hands-on submission CRUD.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType
from repositories.submission_repository import SubmissionRepository
from tests.factories import (
    SubmissionFactory,
    UnvalidatedSubmissionFactory,
    UserFactory,
    create_async,
)

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


class TestSubmissionRepositoryGetByUserAndPhase:
    """Tests for SubmissionRepository.get_by_user_and_phase()."""

    async def test_returns_submissions_for_user_and_phase(
        self, db_session: AsyncSession
    ):
        """Should return all submissions for a user in a specific phase."""
        user = await create_async(UserFactory, db_session)
        # Create submissions in different phases with unique requirement_ids
        sub1 = await create_async(
            SubmissionFactory,
            db_session,
            user_id=user.id,
            phase_id=1,
            requirement_id="phase1-hands-on-1",
        )
        sub2 = await create_async(
            SubmissionFactory,
            db_session,
            user_id=user.id,
            phase_id=1,
            requirement_id="phase1-hands-on-2",
        )
        await create_async(
            SubmissionFactory,
            db_session,
            user_id=user.id,
            phase_id=2,
            requirement_id="phase2-hands-on-1",
        )  # Different phase

        repo = SubmissionRepository(db_session)

        result = await repo.get_by_user_and_phase(user.id, phase_id=1)

        assert len(result) == 2
        result_ids = {s.id for s in result}
        assert sub1.id in result_ids
        assert sub2.id in result_ids

    async def test_returns_empty_when_no_submissions(self, db_session: AsyncSession):
        """Should return empty list when user has no submissions in phase."""
        user = await create_async(UserFactory, db_session)
        repo = SubmissionRepository(db_session)

        result = await repo.get_by_user_and_phase(user.id, phase_id=1)

        assert result == []


class TestSubmissionRepositoryGetValidatedByUser:
    """Tests for SubmissionRepository.get_validated_by_user()."""

    async def test_returns_only_validated_submissions(self, db_session: AsyncSession):
        """Should return only validated submissions."""
        user = await create_async(UserFactory, db_session)
        validated = await create_async(
            SubmissionFactory, db_session, user_id=user.id, is_validated=True
        )
        await create_async(
            UnvalidatedSubmissionFactory,
            db_session,
            user_id=user.id,
            requirement_id="phase1-hands-on-2",
        )

        repo = SubmissionRepository(db_session)

        result = await repo.get_validated_by_user(user.id)

        assert len(result) == 1
        assert result[0].id == validated.id

    async def test_orders_by_phase_and_validated_at(self, db_session: AsyncSession):
        """Should order results by phase_id then validated_at."""
        user = await create_async(UserFactory, db_session)
        # Create in reverse order to verify sorting
        await create_async(
            SubmissionFactory,
            db_session,
            user_id=user.id,
            phase_id=2,
            requirement_id="phase2-hands-on-1",
        )
        await create_async(
            SubmissionFactory,
            db_session,
            user_id=user.id,
            phase_id=1,
            requirement_id="phase1-hands-on-1",
        )

        repo = SubmissionRepository(db_session)

        result = await repo.get_validated_by_user(user.id)

        assert len(result) == 2
        assert result[0].phase_id == 1
        assert result[1].phase_id == 2


class TestSubmissionRepositoryUpsert:
    """Tests for SubmissionRepository.upsert()."""

    async def test_creates_new_submission(self, db_session: AsyncSession):
        """Should create submission when doesn't exist."""
        user = await create_async(UserFactory, db_session)
        repo = SubmissionRepository(db_session)

        submission = await repo.upsert(
            user_id=user.id,
            requirement_id="phase1-hands-on-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=1,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )

        assert submission.user_id == user.id
        assert submission.requirement_id == "phase1-hands-on-1"
        assert submission.is_validated is True

    async def test_updates_existing_submission(self, db_session: AsyncSession):
        """Should update submission when user+requirement already exists."""
        user = await create_async(UserFactory, db_session)

        # Create initial submission directly through repo
        repo = SubmissionRepository(db_session)
        await repo.upsert(
            user_id=user.id,
            requirement_id="phase1-hands-on-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=1,
            submitted_value="old_value",
            extracted_username="olduser",
            is_validated=False,
        )

        # Upsert with new values - returns updated row via RETURNING
        updated_submission = await repo.upsert(
            user_id=user.id,
            requirement_id="phase1-hands-on-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=1,
            submitted_value="new_value",
            extracted_username="newuser",
            is_validated=True,
        )

        # Check the returned submission has updated values
        assert updated_submission.submitted_value == "new_value"
        assert updated_submission.extracted_username == "newuser"
        assert updated_submission.is_validated is True

    async def test_sets_validated_at_when_validated(self, db_session: AsyncSession):
        """Should set validated_at timestamp when is_validated=True."""
        user = await create_async(UserFactory, db_session)
        repo = SubmissionRepository(db_session)

        submission = await repo.upsert(
            user_id=user.id,
            requirement_id="phase1-hands-on-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=1,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )

        assert submission.validated_at is not None

    async def test_validated_at_none_when_not_validated(self, db_session: AsyncSession):
        """Should set validated_at to None when is_validated=False."""
        user = await create_async(UserFactory, db_session)
        repo = SubmissionRepository(db_session)

        submission = await repo.upsert(
            user_id=user.id,
            requirement_id="phase1-hands-on-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=1,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=False,
        )

        assert submission.validated_at is None
