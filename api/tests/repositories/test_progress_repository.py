"""Integration tests for StepProgressRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.progress_repository import StepProgressRepository
from repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration

USER_ID = 70001


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="progressuser")


class TestGetCompletedForTopics:
    async def test_returns_completed_steps_by_topic(
        self, db_session: AsyncSession, user
    ):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, "topic-a", "step-1", 1, 1)
        await repo.create_if_not_exists(USER_ID, "topic-a", "step-2", 2, 1)
        await repo.create_if_not_exists(USER_ID, "topic-b", "step-1", 1, 1)
        await db_session.flush()

        result = await repo.get_completed_for_topics(USER_ID, ["topic-a", "topic-b"])

        assert result["topic-a"] == {"step-1", "step-2"}
        assert result["topic-b"] == {"step-1"}

    async def test_returns_empty_for_no_topics(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        result = await repo.get_completed_for_topics(USER_ID, [])
        assert result == {}

    async def test_excludes_unrequested_topics(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, "topic-x", "step-1", 1, 1)
        await db_session.flush()

        result = await repo.get_completed_for_topics(USER_ID, ["topic-other"])
        assert "topic-x" not in result


class TestCreateIfNotExists:
    async def test_creates_record(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        progress = await repo.create_if_not_exists(USER_ID, "topic-1", "step-1", 1, 1)

        assert progress is not None
        assert progress.user_id == USER_ID
        assert progress.step_id == "step-1"

    async def test_returns_none_on_duplicate(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, "topic-1", "step-1", 1, 1)
        await db_session.flush()

        duplicate = await repo.create_if_not_exists(USER_ID, "topic-1", "step-1", 1, 1)
        assert duplicate is None


class TestDeleteStep:
    async def test_deletes_only_specified_step(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, "topic-1", "step-1", 1, 1)
        await repo.create_if_not_exists(USER_ID, "topic-1", "step-2", 2, 1)
        await repo.create_if_not_exists(USER_ID, "topic-1", "step-3", 3, 1)
        await db_session.flush()

        deleted = await repo.delete_step(USER_ID, "topic-1", "step-2")

        assert deleted == 1
        remaining = await repo.get_completed_step_ids(USER_ID, "topic-1")
        assert remaining == {"step-1", "step-3"}

    async def test_returns_zero_when_nothing_to_delete(
        self, db_session: AsyncSession, user
    ):
        repo = StepProgressRepository(db_session)
        deleted = await repo.delete_step(USER_ID, "topic-1", "step-1")
        assert deleted == 0


class TestGetCompletedStepIds:
    async def test_returns_all_step_ids_for_topic(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, "topic-z", "s1", 1, 1)
        await repo.create_if_not_exists(USER_ID, "topic-z", "s2", 2, 1)
        await db_session.flush()

        ids = await repo.get_completed_step_ids(USER_ID, "topic-z")
        assert ids == {"s1", "s2"}

    async def test_returns_empty_set_for_no_completions(
        self, db_session: AsyncSession, user
    ):
        repo = StepProgressRepository(db_session)
        ids = await repo.get_completed_step_ids(USER_ID, "no-such-topic")
        assert ids == set()
