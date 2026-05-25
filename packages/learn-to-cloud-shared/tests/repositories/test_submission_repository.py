"""Integration tests for SubmissionRepository.

After Phase D.2 (#465 / #460) the repo accepts and returns
``requirement_uuid``. Tests sync the real curriculum to get hold of a
few real UUIDs the FK requires.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumRequirement,
    Submission,
    SubmissionValueKind,
    utcnow,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.submission_values import SubmittedValue

pytestmark = pytest.mark.integration

USER_ID = 80001


def _constraint_name(error: IntegrityError) -> str | None:
    cause = getattr(error.orig, "__cause__", None)
    constraint_name = getattr(cause, "constraint_name", None)
    if isinstance(constraint_name, str):
        return constraint_name
    return None


def _github_value(value: str) -> SubmittedValue:
    return SubmittedValue(kind=SubmissionValueKind.GITHUB_URL, github_url=value)


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="submissionuser")


@pytest.fixture()
async def req_uuids(db_session: AsyncSession) -> list:
    """Sync the curriculum and return GitHub URL requirement UUIDs."""
    clear_cache()
    await sync_curriculum_to_db(db_session)
    result = await db_session.execute(
        select(CurriculumRequirement.uuid)
        .where(CurriculumRequirement.submission_value_kind == "github_url")
        .order_by(CurriculumRequirement.slug)
        .limit(3)
    )
    return [row[0] for row in result.all()]


class TestCreate:
    async def test_creates_submission(self, db_session: AsyncSession, user, req_uuids):
        repo = SubmissionRepository(db_session)
        sub = await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser"),
            extracted_username="testuser",
            is_validated=True,
        )

        assert sub.id is not None
        assert sub.is_validated is True
        assert sub.validated_at is not None
        assert sub.requirement_uuid == req_uuids[0]

    async def test_unvalidated_has_no_validated_at(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        sub = await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/bad"),
            extracted_username=None,
            is_validated=False,
        )

        assert sub.validated_at is None

    async def test_stores_invalid_github_attempts(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)

        sub = await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("http://github.com/testuser"),
            extracted_username=None,
            is_validated=False,
        )

        assert sub.github_url == "http://github.com/testuser"
        assert sub.is_validated is False

    async def test_rejects_blank_typed_value(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        nested = await db_session.begin_nested()
        try:
            with pytest.raises(IntegrityError) as error:
                await repo.create(
                    user_id=USER_ID,
                    requirement_uuid=req_uuids[0],
                    submitted_value=_github_value(""),
                    extracted_username=None,
                    is_validated=False,
                )
        finally:
            await nested.rollback()

        expected = "ck_submissions_typed_value_format"
        assert _constraint_name(error.value) == expected

    async def test_multiple_rows_per_user_requirement_allowed(
        self, db_session: AsyncSession, user, req_uuids
    ):
        """#460: dropping uq_user_requirement_attempt means multiple
        attempts coexist; the PK ``id`` keeps each row unique."""
        repo = SubmissionRepository(db_session)
        sub1 = await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/attempt-1"),
            extracted_username=None,
            is_validated=False,
        )
        sub2 = await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/attempt-2"),
            extracted_username=None,
            is_validated=True,
        )

        assert sub1.id != sub2.id

    async def test_validated_submission_requires_validated_at(
        self, db_session: AsyncSession, user, req_uuids
    ):
        nested = await db_session.begin_nested()
        try:
            db_session.add(
                Submission(
                    user_id=USER_ID,
                    requirement_uuid=req_uuids[0],
                    submitted_value="https://github.com/testuser",
                    submission_value_kind=SubmissionValueKind.GITHUB_URL.value,
                    github_url="https://github.com/testuser",
                    extracted_username="testuser",
                    is_validated=True,
                    validated_at=None,
                    verification_completed=True,
                )
            )

            with pytest.raises(IntegrityError) as error:
                await db_session.flush()
        finally:
            await nested.rollback()

        expected = "ck_submissions_validated_at_when_validated"
        assert _constraint_name(error.value) == expected

    async def test_validated_submission_requires_completed_verification(
        self, db_session: AsyncSession, user, req_uuids
    ):
        nested = await db_session.begin_nested()
        try:
            db_session.add(
                Submission(
                    user_id=USER_ID,
                    requirement_uuid=req_uuids[0],
                    submitted_value="https://github.com/testuser",
                    submission_value_kind=SubmissionValueKind.GITHUB_URL.value,
                    github_url="https://github.com/testuser",
                    extracted_username="testuser",
                    is_validated=True,
                    validated_at=utcnow(),
                    verification_completed=False,
                )
            )

            with pytest.raises(IntegrityError) as error:
                await db_session.flush()
        finally:
            await nested.rollback()

        expected = "ck_submissions_completed_when_validated"
        assert _constraint_name(error.value) == expected


class TestGetByUserAndRequirement:
    async def test_returns_latest_submission(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/old"),
            extracted_username=None,
            is_validated=False,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/new"),
            extracted_username=None,
            is_validated=True,
        )

        latest = await repo.get_by_user_and_requirement(USER_ID, req_uuids[0])
        assert latest is not None
        assert latest.submitted_value == "https://github.com/testuser/new"

    async def test_returns_none_for_missing(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        result = await repo.get_by_user_and_requirement(USER_ID, req_uuids[2])
        assert result is None


class TestGetLatestForRequirements:
    async def test_returns_latest_per_requirement(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/attempt-1"),
            extracted_username=None,
            is_validated=False,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/attempt-2"),
            extracted_username=None,
            is_validated=True,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[1],
            submitted_value=_github_value("https://github.com/testuser/fork-url"),
            extracted_username=None,
            is_validated=True,
        )

        results = await repo.get_latest_for_requirements(USER_ID, req_uuids[:2])

        seen_uuids = {s.requirement_uuid for s in results}
        assert seen_uuids == {req_uuids[0], req_uuids[1]}
        latest_for_first = next(
            s for s in results if s.requirement_uuid == req_uuids[0]
        )
        assert (
            latest_for_first.submitted_value == "https://github.com/testuser/attempt-2"
        )

    async def test_returns_empty_for_no_submissions(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        results = await repo.get_latest_for_requirements(USER_ID, req_uuids[:1])
        assert results == []

    async def test_returns_empty_for_empty_input(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        results = await repo.get_latest_for_requirements(USER_ID, [])
        assert results == []


class TestAreAllRequirementsValidated:
    async def test_returns_true_when_all_validated(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/v1"),
            extracted_username=None,
            is_validated=True,
        )
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[1],
            submitted_value=_github_value("https://github.com/testuser/v2"),
            extracted_username=None,
            is_validated=True,
        )

        assert await repo.are_all_requirements_validated(USER_ID, req_uuids[:2]) is True

    async def test_returns_false_when_some_missing(
        self, db_session: AsyncSession, user, req_uuids
    ):
        repo = SubmissionRepository(db_session)
        await repo.create(
            user_id=USER_ID,
            requirement_uuid=req_uuids[0],
            submitted_value=_github_value("https://github.com/testuser/v1"),
            extracted_username=None,
            is_validated=True,
        )

        assert (
            await repo.are_all_requirements_validated(USER_ID, req_uuids[:2]) is False
        )

    async def test_returns_true_for_empty_list(self, db_session: AsyncSession, user):
        repo = SubmissionRepository(db_session)
        assert await repo.are_all_requirements_validated(USER_ID, []) is True
