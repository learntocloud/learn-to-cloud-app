"""Unit tests for steps_service.

Tests cover:
- _resolve_step validates topic and step existence
- parse_phase_id_from_topic_id extracts phase ID from topic ID strings
- complete_step first-time completion, idempotent re-completion
- uncomplete_step deletion and no-op for non-existent steps
- get_valid_completed_steps filters stale step IDs
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas import LearningStep, Topic
from services.steps_service import (
    StepInvalidStepIdError,
    StepUnknownTopicError,
    _resolve_step,
    complete_step,
    get_valid_completed_steps,
    parse_phase_id_from_topic_id,
    uncomplete_step,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_step(step_id: str, order: int = 0) -> LearningStep:
    return LearningStep(id=step_id, order=order, title=f"Step {step_id}")


def _make_topic(
    topic_id: str = "phase0-topic1",
    steps: list[str] | None = None,
) -> Topic:
    step_ids = steps if steps is not None else ["step-intro", "step-basics"]
    return Topic(
        id=topic_id,
        slug="topic1",
        name="Test Topic",
        description="A test topic",
        order=0,
        learning_steps=[_make_step(sid, i) for i, sid in enumerate(step_ids)],
    )


# ---------------------------------------------------------------------------
# _resolve_step
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveStep:
    def test_valid_step_resolved(self):
        topic = _make_topic(steps=["step-intro", "step-basics"])
        with patch(
            "services.steps_service.get_topic_by_id",
            autospec=True,
            return_value=topic,
        ):
            step_id, order, total = _resolve_step("phase0-topic1", "step-intro")
        assert step_id == "step-intro"
        assert order == 0
        assert total == 2

    def test_unknown_topic_raises(self):
        with patch(
            "services.steps_service.get_topic_by_id",
            autospec=True,
            return_value=None,
        ):
            with pytest.raises(StepUnknownTopicError) as exc_info:
                _resolve_step("nonexistent", "step-1")
            assert exc_info.value.topic_id == "nonexistent"

    def test_invalid_step_id_raises(self):
        topic = _make_topic(steps=["step-intro"])
        with patch(
            "services.steps_service.get_topic_by_id",
            autospec=True,
            return_value=topic,
        ):
            with pytest.raises(StepInvalidStepIdError) as exc_info:
                _resolve_step("phase0-topic1", "nonexistent-step")
            assert exc_info.value.step_id == "nonexistent-step"


# ---------------------------------------------------------------------------
# parse_phase_id_from_topic_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParsePhaseIdFromTopicId:
    def test_phase0(self):
        assert parse_phase_id_from_topic_id("phase0-topic1") == 0

    def test_phase1(self):
        assert parse_phase_id_from_topic_id("phase1-topic5") == 1

    def test_phase6(self):
        assert parse_phase_id_from_topic_id("phase6-topic1") == 6

    def test_invalid_prefix(self):
        assert parse_phase_id_from_topic_id("invalid") is None

    def test_empty_string(self):
        assert parse_phase_id_from_topic_id("") is None

    def test_non_string(self):
        assert parse_phase_id_from_topic_id(123) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# complete_step
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompleteStep:
    @pytest.mark.asyncio
    async def test_first_completion_creates_record(self):
        topic = _make_topic(steps=["step-intro"])
        mock_step_progress = MagicMock(
            topic_id="phase0-topic1",
            step_id="step-intro",
            completed_at=MagicMock(),
        )

        with (
            patch(
                "services.steps_service.get_topic_by_id",
                autospec=True,
                return_value=topic,
            ),
            patch(
                "services.steps_service.StepProgressRepository",
                autospec=True,
            ) as MockRepo,
            patch(
                "services.steps_service.invalidate_progress_cache",
                autospec=True,
            ),
            patch(
                "services.steps_service.update_cached_phase_detail_step",
                autospec=True,
            ),
            patch("core.metrics.STEP_COMPLETED_COUNTER", autospec=True),
        ):
            repo = MockRepo.return_value
            repo.create_if_not_exists = AsyncMock(return_value=mock_step_progress)
            repo.get_completed_step_ids = AsyncMock(return_value={"step-intro"})

            result, completed = await complete_step(
                AsyncMock(), user_id=1, topic_id="phase0-topic1", step_id="step-intro"
            )

        assert result.step_id == "step-intro"
        assert "step-intro" in completed

    @pytest.mark.asyncio
    async def test_idempotent_re_completion(self):
        """Already-completed step returns current state without error."""
        topic = _make_topic(steps=["step-intro"])

        with (
            patch(
                "services.steps_service.get_topic_by_id",
                autospec=True,
                return_value=topic,
            ),
            patch(
                "services.steps_service.StepProgressRepository",
                autospec=True,
            ) as MockRepo,
        ):
            repo = MockRepo.return_value
            repo.create_if_not_exists = AsyncMock(return_value=None)
            repo.get_completed_step_ids = AsyncMock(return_value={"step-intro"})

            result, completed = await complete_step(
                AsyncMock(), user_id=1, topic_id="phase0-topic1", step_id="step-intro"
            )

        assert result.step_id == "step-intro"
        assert "step-intro" in completed


# ---------------------------------------------------------------------------
# uncomplete_step
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUncompleteStep:
    @pytest.mark.asyncio
    async def test_existing_step_deleted(self):
        topic = _make_topic(steps=["step-intro"])

        with (
            patch(
                "services.steps_service.get_topic_by_id",
                autospec=True,
                return_value=topic,
            ),
            patch(
                "services.steps_service.StepProgressRepository",
                autospec=True,
            ) as MockRepo,
            patch(
                "services.steps_service.invalidate_progress_cache",
                autospec=True,
            ) as mock_invalidate,
            patch(
                "services.steps_service.update_cached_phase_detail_step",
                autospec=True,
            ),
            patch("core.metrics.STEP_UNCOMPLETED_COUNTER", autospec=True),
        ):
            repo = MockRepo.return_value
            repo.delete_step = AsyncMock(return_value=1)
            repo.get_completed_step_ids = AsyncMock(return_value=set())

            deleted, completed = await uncomplete_step(
                AsyncMock(), user_id=1, topic_id="phase0-topic1", step_id="step-intro"
            )

        assert deleted == 1
        assert completed == set()
        mock_invalidate.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_nonexistent_step_noop(self):
        """Deleting a step that doesn't exist returns 0, no cache invalidation."""
        topic = _make_topic(steps=["step-intro"])

        with (
            patch(
                "services.steps_service.get_topic_by_id",
                autospec=True,
                return_value=topic,
            ),
            patch(
                "services.steps_service.StepProgressRepository",
                autospec=True,
            ) as MockRepo,
            patch(
                "services.steps_service.invalidate_progress_cache",
                autospec=True,
            ) as mock_invalidate,
            patch(
                "services.steps_service.update_cached_phase_detail_step",
                autospec=True,
            ),
        ):
            repo = MockRepo.return_value
            repo.delete_step = AsyncMock(return_value=0)
            repo.get_completed_step_ids = AsyncMock(return_value=set())

            deleted, completed = await uncomplete_step(
                AsyncMock(), user_id=1, topic_id="phase0-topic1", step_id="step-intro"
            )

        assert deleted == 0
        mock_invalidate.assert_not_called()


# ---------------------------------------------------------------------------
# get_valid_completed_steps
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetValidCompletedSteps:
    @pytest.mark.asyncio
    async def test_filters_stale_step_ids(self):
        topic = _make_topic(steps=["s1", "s2"])

        with patch(
            "services.steps_service.StepProgressRepository",
            autospec=True,
        ) as MockRepo:
            repo = MockRepo.return_value
            repo.get_completed_step_ids = AsyncMock(return_value={"s1", "s2", "s3"})

            result = await get_valid_completed_steps(
                AsyncMock(), user_id=1, topic=topic
            )

        assert result == {"s1", "s2"}
        assert "s3" not in result
