"""Tests for services/steps_service.py - step progress and completion."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.steps_service import (
    StepAlreadyCompletedError,
    StepCompletionResult,
    StepInvalidStepOrderError,
    StepNotUnlockedError,
    StepProgressData,
    StepUnknownTopicError,
    StepValidationError,
    _resolve_total_steps,
    _validate_step_order,
    complete_step,
    get_topic_step_progress,
    uncomplete_step,
)


class TestDataclasses:
    """Test dataclasses."""

    def test_step_progress_data(self):
        """StepProgressData has expected fields."""
        data = StepProgressData(
            topic_id="phase1-topic1",
            completed_steps=[1, 2, 3],
            total_steps=5,
            next_unlocked_step=4,
        )
        assert data.topic_id == "phase1-topic1"
        assert data.completed_steps == [1, 2, 3]
        assert data.total_steps == 5
        assert data.next_unlocked_step == 4

    def test_step_completion_result(self):
        """StepCompletionResult has expected fields."""
        now = datetime.now(UTC)
        result = StepCompletionResult(
            topic_id="phase1-topic1",
            step_order=3,
            completed_at=now,
        )
        assert result.topic_id == "phase1-topic1"
        assert result.step_order == 3
        assert result.completed_at == now


class TestExceptions:
    """Test custom exceptions."""

    def test_step_validation_error(self):
        """StepValidationError is base exception."""
        with pytest.raises(StepValidationError):
            raise StepValidationError("Validation failed")

    def test_step_already_completed_error(self):
        """StepAlreadyCompletedError is raised for duplicate completion."""
        with pytest.raises(StepAlreadyCompletedError):
            raise StepAlreadyCompletedError("Step already done")

    def test_step_not_unlocked_error_message(self):
        """StepNotUnlockedError includes completed and required steps."""
        error = StepNotUnlockedError(
            completed_steps=[1, 2],
            required_steps=[1, 2, 3],
        )
        assert error.completed_steps == [1, 2]
        assert error.required_steps == [1, 2, 3]
        assert "1, 2" in str(error)
        assert "1, 2, 3" in str(error)

    def test_step_unknown_topic_error(self):
        """StepUnknownTopicError for invalid topic."""
        with pytest.raises(StepUnknownTopicError, match="topic"):
            raise StepUnknownTopicError("Unknown topic_id: bad")

    def test_step_invalid_step_order_error(self):
        """StepInvalidStepOrderError for out of range step."""
        with pytest.raises(StepInvalidStepOrderError, match="too high"):
            raise StepInvalidStepOrderError("Step 99 is too high")


class TestResolveTotalSteps:
    """Tests for _resolve_total_steps helper."""

    def test_returns_step_count(self):
        """Returns count of learning steps in topic."""
        mock_topic = MagicMock()
        mock_topic.learning_steps = [MagicMock(), MagicMock(), MagicMock()]

        with patch("services.steps_service.get_topic_by_id", return_value=mock_topic):
            total = _resolve_total_steps("phase1-topic1")

        assert total == 3

    def test_unknown_topic_raises(self):
        """Raises StepUnknownTopicError for nonexistent topic."""
        with patch("services.steps_service.get_topic_by_id", return_value=None):
            with pytest.raises(StepUnknownTopicError, match="Unknown"):
                _resolve_total_steps("nonexistent")


class TestValidateStepOrder:
    """Tests for _validate_step_order helper."""

    def test_valid_step_returns_total(self):
        """Valid step order returns total steps."""
        mock_topic = MagicMock()
        mock_topic.learning_steps = [MagicMock()] * 5  # 5 steps

        with patch("services.steps_service.get_topic_by_id", return_value=mock_topic):
            total = _validate_step_order("phase1-topic1", 3)

        assert total == 5

    def test_step_zero_invalid(self):
        """Step 0 is invalid."""
        mock_topic = MagicMock()
        mock_topic.learning_steps = [MagicMock()] * 5

        with patch("services.steps_service.get_topic_by_id", return_value=mock_topic):
            with pytest.raises(StepInvalidStepOrderError, match="between 1 and 5"):
                _validate_step_order("phase1-topic1", 0)

    def test_step_too_high_invalid(self):
        """Step beyond total is invalid."""
        mock_topic = MagicMock()
        mock_topic.learning_steps = [MagicMock()] * 5

        with patch("services.steps_service.get_topic_by_id", return_value=mock_topic):
            with pytest.raises(StepInvalidStepOrderError, match="between 1 and 5"):
                _validate_step_order("phase1-topic1", 10)


class TestGetTopicStepProgress:
    """Tests for get_topic_step_progress function."""

    @pytest.fixture
    def mock_topic(self):
        """Mock topic with 5 steps."""
        topic = MagicMock()
        topic.learning_steps = [MagicMock()] * 5
        return topic

    @pytest.mark.asyncio
    async def test_no_completed_steps(self, mock_topic):
        """User with no progress starts at step 1."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_step_orders.return_value = set()

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
        ):
            result = await get_topic_step_progress(mock_db, "user-123", "phase1-topic1")

        assert result.completed_steps == []
        assert result.total_steps == 5
        assert result.next_unlocked_step == 1

    @pytest.mark.asyncio
    async def test_some_steps_completed(self, mock_topic):
        """Next unlocked is one after highest completed."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_step_orders.return_value = {1, 2, 3}

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
        ):
            result = await get_topic_step_progress(mock_db, "user-123", "phase1-topic1")

        assert result.completed_steps == [1, 2, 3]
        assert result.next_unlocked_step == 4

    @pytest.mark.asyncio
    async def test_all_steps_completed(self, mock_topic):
        """When all completed, next unlocked is last step."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_step_orders.return_value = {1, 2, 3, 4, 5}

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
        ):
            result = await get_topic_step_progress(mock_db, "user-123", "phase1-topic1")

        assert result.completed_steps == [1, 2, 3, 4, 5]
        assert result.next_unlocked_step == 5

    @pytest.mark.asyncio
    async def test_admin_has_all_unlocked(self, mock_topic):
        """Admin users have all steps unlocked."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_completed_step_orders.return_value = set()

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
        ):
            result = await get_topic_step_progress(
                mock_db, "admin-user", "phase1-topic1", is_admin=True
            )

        assert result.next_unlocked_step == 5  # All 5 steps unlocked


class TestCompleteStep:
    """Tests for complete_step function."""

    @pytest.fixture
    def mock_topic(self):
        """Mock topic with 5 steps."""
        topic = MagicMock()
        topic.learning_steps = [MagicMock()] * 5
        return topic

    @pytest.mark.asyncio
    async def test_complete_first_step(self, mock_topic):
        """First step can always be completed."""
        mock_db = MagicMock()
        mock_step_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_step_repo.exists.return_value = False
        mock_step_progress = MagicMock()
        mock_step_progress.topic_id = "phase1-topic1"
        mock_step_progress.step_order = 1
        mock_step_progress.completed_at = datetime.now(UTC)
        mock_step_repo.create.return_value = mock_step_progress

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_step_repo,
            ),
            patch(
                "services.steps_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache"),
            patch("services.steps_service.log_metric"),
            patch("services.steps_service.add_custom_attribute"),
        ):
            result = await complete_step(mock_db, "user-123", "phase1-topic1", 1)

        assert result.step_order == 1
        mock_step_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_already_completed_raises(self, mock_topic):
        """Cannot complete a step twice."""
        mock_db = MagicMock()
        mock_step_repo = AsyncMock()
        mock_step_repo.exists.return_value = True

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_step_repo,
            ),
            patch("services.steps_service.add_custom_attribute"),
        ):
            with pytest.raises(StepAlreadyCompletedError):
                await complete_step(mock_db, "user-123", "phase1-topic1", 1)

    @pytest.mark.asyncio
    async def test_complete_step_without_prerequisites_raises(self, mock_topic):
        """Cannot complete step 3 without completing 1 and 2."""
        mock_db = MagicMock()
        mock_step_repo = AsyncMock()
        mock_step_repo.exists.return_value = False
        mock_step_repo.get_completed_step_orders.return_value = {1}  # Only step 1

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_step_repo,
            ),
            patch("services.steps_service.add_custom_attribute"),
        ):
            with pytest.raises(StepNotUnlockedError) as exc_info:
                await complete_step(mock_db, "user-123", "phase1-topic1", 3)

            assert exc_info.value.completed_steps == [1]
            assert 2 in exc_info.value.required_steps

    @pytest.mark.asyncio
    async def test_admin_can_skip_steps(self, mock_topic):
        """Admin can complete any step without prerequisites."""
        mock_db = MagicMock()
        mock_step_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_step_repo.exists.return_value = False
        # Admin skips to step 5 with no prior completion
        mock_step_repo.get_completed_step_orders.return_value = set()

        mock_step_progress = MagicMock()
        mock_step_progress.topic_id = "phase1-topic1"
        mock_step_progress.step_order = 5
        mock_step_progress.completed_at = datetime.now(UTC)
        mock_step_repo.create.return_value = mock_step_progress

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_step_repo,
            ),
            patch(
                "services.steps_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache"),
            patch("services.steps_service.log_metric"),
            patch("services.steps_service.add_custom_attribute"),
        ):
            result = await complete_step(
                mock_db, "admin", "phase1-topic1", 5, is_admin=True
            )

        assert result.step_order == 5

    @pytest.mark.asyncio
    async def test_complete_logs_activity(self, mock_topic):
        """Step completion logs activity."""
        mock_db = MagicMock()
        mock_step_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_step_repo.exists.return_value = False
        mock_step_progress = MagicMock()
        mock_step_progress.topic_id = "phase1-topic1"
        mock_step_progress.step_order = 1
        mock_step_progress.completed_at = datetime.now(UTC)
        mock_step_repo.create.return_value = mock_step_progress

        from models import ActivityType

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_step_repo,
            ),
            patch(
                "services.steps_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache"),
            patch("services.steps_service.log_metric"),
            patch("services.steps_service.add_custom_attribute"),
        ):
            await complete_step(mock_db, "user-123", "phase1-topic1", 1)

        mock_activity_repo.log_activity.assert_called_once()
        call_kwargs = mock_activity_repo.log_activity.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["activity_type"] == ActivityType.STEP_COMPLETE
        assert call_kwargs["reference_id"] == "phase1-topic1:step1"

    @pytest.mark.asyncio
    async def test_complete_invalidates_cache(self, mock_topic):
        """Step completion invalidates progress cache."""
        mock_db = MagicMock()
        mock_step_repo = AsyncMock()
        mock_activity_repo = AsyncMock()
        mock_invalidate = MagicMock()

        mock_step_repo.exists.return_value = False
        mock_step_progress = MagicMock()
        mock_step_progress.topic_id = "phase1-topic1"
        mock_step_progress.step_order = 1
        mock_step_progress.completed_at = datetime.now(UTC)
        mock_step_repo.create.return_value = mock_step_progress

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_step_repo,
            ),
            patch(
                "services.steps_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache", mock_invalidate),
            patch("services.steps_service.log_metric"),
            patch("services.steps_service.add_custom_attribute"),
        ):
            await complete_step(mock_db, "user-123", "phase1-topic1", 1)

        mock_invalidate.assert_called_once_with("user-123")


class TestUncompleteStep:
    """Tests for uncomplete_step function."""

    @pytest.fixture
    def mock_topic(self):
        """Mock topic with 5 steps."""
        topic = MagicMock()
        topic.learning_steps = [MagicMock()] * 5
        return topic

    @pytest.mark.asyncio
    async def test_uncomplete_deletes_step_and_following(self, mock_topic):
        """Uncompleting a step deletes it and all following steps."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.delete_from_step.return_value = 3  # Deleted steps 3, 4, 5

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache"),
        ):
            deleted = await uncomplete_step(mock_db, "user-123", "phase1-topic1", 3)

        assert deleted == 3
        mock_repo.delete_from_step.assert_called_once_with(
            "user-123", "phase1-topic1", 3
        )

    @pytest.mark.asyncio
    async def test_uncomplete_invalidates_cache_when_deleted(self, mock_topic):
        """Cache invalidated when steps are deleted."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.delete_from_step.return_value = 2
        mock_invalidate = MagicMock()

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache", mock_invalidate),
        ):
            await uncomplete_step(mock_db, "user-123", "phase1-topic1", 1)

        mock_invalidate.assert_called_once_with("user-123")

    @pytest.mark.asyncio
    async def test_uncomplete_no_cache_invalidation_when_nothing_deleted(
        self, mock_topic
    ):
        """No cache invalidation when no steps deleted."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.delete_from_step.return_value = 0  # Nothing deleted
        mock_invalidate = MagicMock()

        with (
            patch("services.steps_service.get_topic_by_id", return_value=mock_topic),
            patch(
                "services.steps_service.StepProgressRepository",
                return_value=mock_repo,
            ),
            patch("services.steps_service.invalidate_progress_cache", mock_invalidate),
        ):
            await uncomplete_step(mock_db, "user-123", "phase1-topic1", 1)

        mock_invalidate.assert_not_called()

    @pytest.mark.asyncio
    async def test_uncomplete_validates_step_order(self, mock_topic):
        """Uncomplete validates step order is in range."""
        mock_db = MagicMock()

        with patch("services.steps_service.get_topic_by_id", return_value=mock_topic):
            with pytest.raises(StepInvalidStepOrderError):
                await uncomplete_step(mock_db, "user-123", "phase1-topic1", 99)
