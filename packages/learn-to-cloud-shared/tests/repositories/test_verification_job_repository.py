"""Integration tests for VerificationJobRepository."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumRequirement,
    Submission,
    SubmissionValueKind,
    VerificationJob,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_job_repository import (
    LinkResult,
    VerificationJobRepository,
)
from learn_to_cloud_shared.submission_values import SubmittedValue

pytestmark = pytest.mark.integration

USER_ID = 81001


def _github_value(value: str) -> SubmittedValue:
    return SubmittedValue(kind=SubmissionValueKind.GITHUB_URL, github_url=value)


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="verificationjobuser")


@pytest.fixture()
async def req_uuid(db_session: AsyncSession) -> UUID:
    """Sync curriculum and return a GitHub URL requirement UUID."""
    clear_cache()
    await sync_curriculum_to_db(db_session)
    result = await db_session.execute(
        select(CurriculumRequirement.uuid)
        .where(CurriculumRequirement.submission_value_kind == "github_url")
        .order_by(CurriculumRequirement.slug)
        .limit(1)
    )
    return result.scalar_one()


async def _create_job(
    repo: VerificationJobRepository,
    requirement_uuid: UUID,
):
    return await repo.create(
        user_id=USER_ID,
        requirement_uuid=requirement_uuid,
        submitted_value=_github_value("https://github.com/testuser"),
        extracted_username="testuser",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )


async def _create_submission(
    db_session: AsyncSession,
    requirement_uuid: UUID,
    *,
    is_validated: bool = True,
    verification_completed: bool = True,
):
    return await SubmissionRepository(db_session).create(
        user_id=USER_ID,
        requirement_uuid=requirement_uuid,
        submitted_value=_github_value("https://github.com/testuser"),
        extracted_username="testuser",
        is_validated=is_validated,
        verification_completed=verification_completed,
    )


class TestCreate:
    async def test_creates_verification_job(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)

        job = await _create_job(repo, req_uuid)

        assert isinstance(job.id, UUID)
        assert job.user_id == USER_ID
        assert job.requirement_uuid == req_uuid
        assert job.traceparent is not None
        assert job.created_at is not None
        assert job.result_submission_id is None

    async def test_creates_verification_job_with_explicit_id(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        """The unified-attempt submission path shares one UUID between the
        ``verification_attempts`` row and this compatibility job row."""
        repo = VerificationJobRepository(db_session)
        shared_id = uuid4()

        job = await repo.create(
            id=shared_id,
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_github_value("https://github.com/testuser"),
        )

        assert job.id == shared_id

    async def test_create_or_get_active_returns_existing_active_job(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)

        first, first_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_github_value("https://github.com/testuser/token-1"),
        )
        second, second_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_github_value("https://github.com/testuser/token-2"),
        )

        assert first_created is True
        assert second_created is False
        assert second.id == first.id
        assert second.submitted_value == "https://github.com/testuser/token-1"

        count = await db_session.scalar(
            select(func.count()).select_from(VerificationJob)
        )
        assert count == 1

    async def test_linked_job_allows_new_active_job(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        """After ``link_submission`` flips a job out of the unlinked
        partial unique index, a follow-up submit must succeed.
        Mirrors the failure-retry path: persist a Submission and link
        it, then submit again."""
        repo = VerificationJobRepository(db_session)

        first, first_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_github_value("https://github.com/testuser/token-1"),
        )
        submission = await _create_submission(
            db_session,
            req_uuid,
            is_validated=False,
            verification_completed=True,
        )
        link = await repo.link_submission(first.id, submission.id)
        assert link is LinkResult.LINKED

        second, second_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_github_value("https://github.com/testuser/token-2"),
        )

        assert first_created is True
        assert second_created is True
        assert second.id != first.id
        assert second.submitted_value == "https://github.com/testuser/token-2"


class TestFind:
    async def test_gets_active_and_latest_jobs(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)
        first = await _create_job(repo, req_uuid)
        deleted = await repo.delete_active(first.id)
        assert deleted is True
        second = await _create_job(repo, req_uuid)

        active = await repo.get_active_for_requirement(USER_ID, req_uuid)
        latest = await repo.get_latest_for_requirement(USER_ID, req_uuid)

        assert active is not None
        assert active.id == second.id
        assert latest is not None
        assert latest.id == second.id

    async def test_returns_none_for_missing_job(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)

        result = await repo.get_latest_for_requirement(USER_ID, uuid4())

        assert result is None


class TestLinkSubmission:
    """``link_submission`` is the executor's terminal write."""

    async def test_links_unlinked_job(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo, req_uuid)
        submission = await _create_submission(db_session, req_uuid)

        before = job.updated_at
        result = await repo.link_submission(job.id, submission.id)
        await db_session.commit()

        assert result is LinkResult.LINKED
        loaded = await repo.get_by_id(job.id)
        assert loaded is not None
        assert loaded.result_submission_id == submission.id
        assert loaded.updated_at >= before

    async def test_second_call_returns_already_linked(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        """Idempotency check: a Durable activity retry that re-runs
        ``link_submission`` sees ``ALREADY_LINKED`` instead of writing
        again."""
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo, req_uuid)
        submission = await _create_submission(db_session, req_uuid)

        first = await repo.link_submission(job.id, submission.id)
        # Even if the retry passes a different submission id, the row's
        # existing link wins. Reuse the same id for simplicity.
        second = await repo.link_submission(job.id, submission.id)

        assert first is LinkResult.LINKED
        assert second is LinkResult.ALREADY_LINKED

    async def test_missing_job_returns_missing(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)
        submission = await _create_submission(db_session, req_uuid)

        result = await repo.link_submission(
            UUID("00000000-0000-0000-0000-000000000000"),
            submission.id,
        )

        assert result is LinkResult.MISSING


class TestDeleteActive:
    """``delete_active`` guards against racing the persist activity."""

    async def test_deletes_active_unlinked_row(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo, req_uuid)

        deleted = await repo.delete_active(job.id)
        await db_session.commit()

        assert deleted is True
        remaining = await db_session.execute(
            select(func.count()).select_from(VerificationJob)
        )
        assert remaining.scalar() == 0

    async def test_refuses_when_result_submission_linked(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo, req_uuid)
        submission = await _create_submission(db_session, req_uuid)
        await repo.link_submission(job.id, submission.id)

        deleted = await repo.delete_active(job.id)

        assert deleted is False
        loaded = await repo.get_by_id(job.id)
        assert loaded is not None
        assert loaded.result_submission_id == submission.id

    async def test_linked_submission_delete_is_restricted(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo, req_uuid)
        submission = await _create_submission(db_session, req_uuid)
        await repo.link_submission(job.id, submission.id)

        with pytest.raises(IntegrityError):
            await db_session.execute(
                delete(Submission).where(Submission.id == submission.id)
            )
            await db_session.flush()

    async def test_unknown_id_returns_false(
        self,
        db_session: AsyncSession,
        user,
        req_uuid: UUID,
    ):
        repo = VerificationJobRepository(db_session)

        deleted = await repo.delete_active(UUID("00000000-0000-0000-0000-000000000000"))

        assert deleted is False
