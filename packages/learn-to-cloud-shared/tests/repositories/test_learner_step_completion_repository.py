"""Integration tests for curriculum-independent learner completions."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import LearnerStepCompletion, utcnow
from learn_to_cloud_shared.repositories.learner_step_completion_repository import (
    LearnerStepCompletionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration

USER_ID = 71001


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="completionuser")


class TestCreateIfNotExists:
    async def test_creates_record(self, db_session: AsyncSession, user):
        step_uuid = uuid4()
        repo = LearnerStepCompletionRepository(db_session)

        await repo.create_if_not_exists(user_id=USER_ID, step_uuid=step_uuid)
        completion = await db_session.get(LearnerStepCompletion, (USER_ID, step_uuid))

        assert completion is not None
        assert completion.user_id == USER_ID
        assert completion.step_uuid == step_uuid
        assert completion.completed_at is not None

    async def test_duplicate_preserves_completed_at(
        self, db_session: AsyncSession, user
    ):
        step_uuid = uuid4()
        completed_at = utcnow()
        repo = LearnerStepCompletionRepository(db_session)
        await repo.create_if_not_exists(
            user_id=USER_ID, step_uuid=step_uuid, completed_at=completed_at
        )
        await db_session.flush()

        await repo.create_if_not_exists(user_id=USER_ID, step_uuid=step_uuid)
        stored = (
            await db_session.execute(select(LearnerStepCompletion.__table__))
        ).one()
        assert (stored.user_id, stored.step_uuid, stored.completed_at) == (
            USER_ID,
            step_uuid,
            completed_at,
        )

    async def test_accepts_explicit_completed_at(self, db_session: AsyncSession, user):
        """Preserve a caller-supplied completion timestamp."""
        step_uuid = uuid4()
        shared_completed_at = utcnow()
        repo = LearnerStepCompletionRepository(db_session)

        await repo.create_if_not_exists(
            user_id=USER_ID,
            step_uuid=step_uuid,
            completed_at=shared_completed_at,
        )

        completion = await db_session.get(LearnerStepCompletion, (USER_ID, step_uuid))
        assert completion is not None
        assert completion.completed_at == shared_completed_at


class TestDelete:
    async def test_deletes_only_specified_step(self, db_session: AsyncSession, user):
        step_a, step_b = uuid4(), uuid4()
        completed_at = utcnow()
        repo = LearnerStepCompletionRepository(db_session)
        await repo.create_if_not_exists(user_id=USER_ID, step_uuid=step_a)
        await repo.create_if_not_exists(
            user_id=USER_ID, step_uuid=step_b, completed_at=completed_at
        )
        await db_session.flush()

        await repo.delete(user_id=USER_ID, step_uuid=step_a)

        remaining = (
            await db_session.execute(select(LearnerStepCompletion.__table__))
        ).one()
        assert (remaining.user_id, remaining.step_uuid, remaining.completed_at) == (
            USER_ID,
            step_b,
            completed_at,
        )

    async def test_delete_nonexistent_is_noop(self, db_session: AsyncSession, user):
        repo = LearnerStepCompletionRepository(db_session)
        await repo.delete(user_id=USER_ID, step_uuid=uuid4())
        assert (await db_session.scalars(select(LearnerStepCompletion))).all() == []


class TestGetCompletedStepUuids:
    async def test_returns_only_completed_and_requested(
        self, db_session: AsyncSession, user
    ):
        completed, other_completed, uncompleted = uuid4(), uuid4(), uuid4()
        repo = LearnerStepCompletionRepository(db_session)
        await repo.create_if_not_exists(user_id=USER_ID, step_uuid=completed)
        await repo.create_if_not_exists(user_id=USER_ID, step_uuid=other_completed)
        await db_session.flush()

        result = await repo.get_completed_step_uuids(USER_ID, [completed, uncompleted])

        assert result == {completed}

    async def test_empty_candidate_list_returns_empty_set_without_query(
        self, db_session: AsyncSession, user
    ):
        repo = LearnerStepCompletionRepository(db_session)
        assert await repo.get_completed_step_uuids(USER_ID, []) == set()

    async def test_ignores_other_users_completions(
        self, db_session: AsyncSession, user
    ):
        other_user_id = 71002
        await UserRepository(db_session).upsert(
            other_user_id, github_username="otheruser"
        )
        step_uuid = uuid4()
        repo = LearnerStepCompletionRepository(db_session)
        await repo.create_if_not_exists(user_id=other_user_id, step_uuid=step_uuid)
        await db_session.flush()

        result = await repo.get_completed_step_uuids(USER_ID, [step_uuid])

        assert result == set()
