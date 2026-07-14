"""Unit tests for steps_service after the step_uuid simplification."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.schemas import (
    LearningStep,
    Topic,
)

from learn_to_cloud.services.steps_service import (
    StepNotFoundError,
    complete_step,
    get_valid_completed_steps,
    uncomplete_step,
)


def _make_step(slug: str = "step-1") -> LearningStep:
    return LearningStep(uuid=uuid4(), slug=slug, order=1)


def _make_topic(steps: list[LearningStep] | None = None) -> Topic:
    return Topic(
        uuid=uuid4(),
        slug="topic1",
        name="Test Topic",
        description="d",
        order=0,
        learning_steps=steps or [_make_step()],
    )


@pytest.mark.unit
class TestCompleteStep:
    @pytest.mark.asyncio
    async def test_first_completion_creates_record(self):
        step = _make_step()
        topic = _make_topic([step])
        mock_progress = MagicMock(
            user_id=1, step_uuid=step.uuid, completed_at=MagicMock()
        )

        with (
            patch(
                "learn_to_cloud.services.steps_service.get_topic_containing_step",
                return_value=(topic, step),
            ),
            patch(
                "learn_to_cloud.services.steps_service.StepProgressRepository",
                autospec=True,
            ) as MockRepo,
        ):
            repo = MockRepo.return_value
            repo.create_if_not_exists = AsyncMock(return_value=mock_progress)
            repo.get_completed_step_uuids = AsyncMock(return_value={step.uuid})

            result, returned_topic, completed = await complete_step(
                AsyncMock(), user_id=1, step_uuid=step.uuid
            )

        assert result.step_slug == step.slug
        assert returned_topic.uuid == topic.uuid
        assert step.uuid in completed

    @pytest.mark.asyncio
    async def test_unknown_step_raises(self):
        with patch(
            "learn_to_cloud.services.steps_service.get_topic_containing_step",
            return_value=None,
        ):
            with pytest.raises(StepNotFoundError):
                await complete_step(AsyncMock(), user_id=1, step_uuid=uuid4())


@pytest.mark.unit
class TestUncompleteStep:
    @pytest.mark.asyncio
    async def test_existing_step_deleted(self):
        step = _make_step()
        topic = _make_topic([step])

        with (
            patch(
                "learn_to_cloud.services.steps_service.get_topic_containing_step",
                return_value=(topic, step),
            ),
            patch(
                "learn_to_cloud.services.steps_service.StepProgressRepository",
                autospec=True,
            ) as MockRepo,
        ):
            repo = MockRepo.return_value
            repo.delete_step = AsyncMock(return_value=1)
            repo.get_completed_step_uuids = AsyncMock(return_value=set())

            deleted, returned_topic, returned_step, completed = await uncomplete_step(
                AsyncMock(), user_id=1, step_uuid=step.uuid
            )

        assert deleted == 1
        assert returned_step.uuid == step.uuid
        assert completed == set()


@pytest.mark.unit
class TestGetValidCompletedSteps:
    @pytest.mark.asyncio
    async def test_returns_completed_subset(self):
        s1 = _make_step("s1")
        s2 = _make_step("s2")
        topic = _make_topic([s1, s2])

        with patch(
            "learn_to_cloud.services.steps_service.StepProgressRepository",
            autospec=True,
        ) as MockRepo:
            repo = MockRepo.return_value
            repo.get_completed_step_uuids = AsyncMock(return_value={s1.uuid})

            result = await get_valid_completed_steps(
                AsyncMock(), user_id=1, topic=topic
            )

        assert result == {s1.uuid}
