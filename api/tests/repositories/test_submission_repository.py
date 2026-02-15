"""Integration tests for SubmissionRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType
from repositories.submission_repository import SubmissionRepository
from repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration

USER_ID = 80001


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="submissionuser")


class TestCreate:
    async def test_creates_submission(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        sub = await repo.create(
            user_id=USER_ID,
            requirement_id="req-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )

        assert sub.id is not None
        assert sub.attempt_number == 1
        assert sub.is_validated is True
        assert sub.validated_at is not None

    async def test_auto_increments_attempt_number(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        sub1 = await repo.create(
            user_id=USER_ID,
            requirement_id="req-inc",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token-1",
            extracted_username=None,
            is_validated=False,
        )
        sub2 = await repo.create(
            user_id=USER_ID,
            requirement_id="req-inc",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token-2",
            extracted_username=None,
            is_validated=True,
        )

        assert sub1.attempt_number == 1
        assert sub2.attempt_number == 2

    async def test_unvalidated_has_no_validated_at(
        self, db_session: AsyncSession, user
    ):
        repo = SubmissionRepository(db_session)
        sub = await repo.create(
            user_id=USER_ID,
            requirement_id="req-fail",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="bad-value",
            extracted_username=None,
            is_validated=False,
        )

        assert sub.validated_at is None


class TestGetByUserAndRequirement:
    async def test_returns_latest_submission(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_id="req-latest",
            submission_type=SubmissionType.PROFILE_README,
            phase_id=1,
            submitted_value="old",
            extracted_username=None,
            is_validated=False,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_id="req-latest",
            submission_type=SubmissionType.PROFILE_README,
            phase_id=1,
            submitted_value="new",
            extracted_username=None,
            is_validated=True,
        )

        latest = await repo.get_by_user_and_requirement(USER_ID, "req-latest")
        assert latest is not None
        assert latest.submitted_value == "new"
        assert latest.attempt_number == 2

    async def test_returns_none_for_missing(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        result = await repo.get_by_user_and_requirement(USER_ID, "nonexistent")
        assert result is None


class TestGetByUserAndPhase:
    async def test_returns_latest_per_requirement(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        # Two submissions for req-a, one for req-b
        await repo.create(
            user_id=USER_ID,
            requirement_id="req-a",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="attempt-1",
            extracted_username=None,
            is_validated=False,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_id="req-a",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="attempt-2",
            extracted_username=None,
            is_validated=True,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_id="req-b",
            submission_type=SubmissionType.REPO_FORK,
            phase_id=1,
            submitted_value="fork-url",
            extracted_username=None,
            is_validated=True,
        )

        results = await repo.get_by_user_and_phase(USER_ID, phase_id=1)

        req_ids = {s.requirement_id for s in results}
        assert req_ids == {"req-a", "req-b"}
        # Should return only latest for req-a
        req_a = next(s for s in results if s.requirement_id == "req-a")
        assert req_a.submitted_value == "attempt-2"

    async def test_returns_empty_for_no_submissions(
        self, db_session: AsyncSession, user
    ):
        repo = SubmissionRepository(db_session)
        results = await repo.get_by_user_and_phase(USER_ID, phase_id=99)
        assert results == []


class TestAreAllRequirementsValidated:
    async def test_returns_true_when_all_validated(
        self, db_session: AsyncSession, user
    ):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_id="r1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="v1",
            extracted_username=None,
            is_validated=True,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_id="r2",
            submission_type=SubmissionType.PROFILE_README,
            phase_id=1,
            submitted_value="v2",
            extracted_username=None,
            is_validated=True,
        )

        assert await repo.are_all_requirements_validated(USER_ID, ["r1", "r2"]) is True

    async def test_returns_false_when_some_missing(
        self, db_session: AsyncSession, user
    ):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_id="r1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="v1",
            extracted_username=None,
            is_validated=True,
        )

        assert await repo.are_all_requirements_validated(USER_ID, ["r1", "r2"]) is False

    async def test_returns_true_for_empty_list(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        assert await repo.are_all_requirements_validated(USER_ID, []) is True
