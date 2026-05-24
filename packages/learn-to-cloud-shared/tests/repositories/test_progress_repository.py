"""Integration tests for StepProgressRepository.

After Phase D.1c (#465) the repository accepts and returns curriculum
step UUIDs. The FK to ``steps.uuid`` means rows can only be inserted
for active steps in the synced curriculum, so each test seeds the
real curriculum via ``sync_curriculum_to_db`` and pulls two arbitrary
step UUIDs out of it.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import CurriculumStep
from learn_to_cloud_shared.repositories.progress_repository import (
    StepProgressRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration

USER_ID = 70001


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="progressuser")


@pytest.fixture()
async def step_uuids(db_session: AsyncSession) -> list:
    """Sync the real curriculum and return the first 3 step UUIDs."""
    clear_cache()
    await sync_curriculum_to_db(db_session)
    result = await db_session.execute(
        select(CurriculumStep.uuid).order_by(CurriculumStep.uuid).limit(3)
    )
    return [row[0] for row in result.all()]


class TestGetCompletedStepUuids:
    async def test_returns_completed_uuids(
        self, db_session: AsyncSession, user, step_uuids: list
    ):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, step_uuids[0])
        await repo.create_if_not_exists(USER_ID, step_uuids[1])
        await db_session.flush()

        result = await repo.get_completed_step_uuids(USER_ID, step_uuids)

        assert result == {step_uuids[0], step_uuids[1]}

    async def test_returns_empty_for_no_uuids(self, db_session: AsyncSession, user):
        repo = StepProgressRepository(db_session)
        result = await repo.get_completed_step_uuids(USER_ID, [])
        assert result == set()

    async def test_excludes_unrequested_uuids(
        self, db_session: AsyncSession, user, step_uuids: list
    ):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, step_uuids[0])
        await db_session.flush()

        # Ask only about step 2, which is NOT completed
        result = await repo.get_completed_step_uuids(USER_ID, [step_uuids[1]])
        assert result == set()


class TestCreateIfNotExists:
    async def test_creates_record(
        self, db_session: AsyncSession, user, step_uuids: list
    ):
        repo = StepProgressRepository(db_session)
        progress = await repo.create_if_not_exists(USER_ID, step_uuids[0])

        assert progress is not None
        assert progress.user_id == USER_ID
        assert progress.step_uuid == step_uuids[0]

    async def test_returns_none_on_duplicate(
        self, db_session: AsyncSession, user, step_uuids: list
    ):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, step_uuids[0])
        await db_session.flush()

        duplicate = await repo.create_if_not_exists(USER_ID, step_uuids[0])
        assert duplicate is None


class TestDeleteStep:
    async def test_deletes_only_specified_step(
        self, db_session: AsyncSession, user, step_uuids: list
    ):
        repo = StepProgressRepository(db_session)
        await repo.create_if_not_exists(USER_ID, step_uuids[0])
        await repo.create_if_not_exists(USER_ID, step_uuids[1])
        await repo.create_if_not_exists(USER_ID, step_uuids[2])
        await db_session.flush()

        deleted = await repo.delete_step(USER_ID, step_uuids[1])

        assert deleted == 1
        remaining = await repo.get_completed_step_uuids(USER_ID, step_uuids)
        assert remaining == {step_uuids[0], step_uuids[2]}

    async def test_returns_zero_when_nothing_to_delete(
        self, db_session: AsyncSession, user, step_uuids: list
    ):
        repo = StepProgressRepository(db_session)
        deleted = await repo.delete_step(USER_ID, step_uuids[0])
        assert deleted == 0
