"""Tests for services/activity_service.py - streak, heatmap, and activity logging."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine

from models import ActivityType
from services.activity_service import (
    ActivityResult,
    HeatmapData,
    HeatmapDay,
    StreakData,
    get_heatmap_data,
    get_streak_data,
    log_activity,
)


class TestStreakDataDataclass:
    """Test StreakData dataclass."""

    def test_streak_data_fields(self):
        """StreakData has all expected fields."""
        data = StreakData(
            current_streak=5,
            longest_streak=10,
            total_activity_days=20,
            last_activity_date=date(2026, 1, 17),
            streak_alive=True,
        )
        assert data.current_streak == 5
        assert data.longest_streak == 10
        assert data.total_activity_days == 20
        assert data.last_activity_date == date(2026, 1, 17)
        assert data.streak_alive is True

    def test_streak_data_with_none_last_activity(self):
        """StreakData can have None for last_activity_date."""
        data = StreakData(
            current_streak=0,
            longest_streak=0,
            total_activity_days=0,
            last_activity_date=None,
            streak_alive=False,
        )
        assert data.last_activity_date is None


class TestHeatmapDataclasses:
    """Test HeatmapDay and HeatmapData dataclasses."""

    def test_heatmap_day(self):
        """HeatmapDay has expected fields."""
        day = HeatmapDay(
            date=date(2026, 1, 17),
            count=5,
            activity_types=["step_completed", "question_passed"],
        )
        assert day.date == date(2026, 1, 17)
        assert day.count == 5
        assert len(day.activity_types) == 2

    def test_heatmap_data(self):
        """HeatmapData has expected fields."""
        data = HeatmapData(
            days=[],
            start_date=date(2025, 1, 17),
            end_date=date(2026, 1, 17),
            total_activities=100,
        )
        assert data.total_activities == 100


class TestActivityResultDataclass:
    """Test ActivityResult dataclass."""

    def test_activity_result_fields(self):
        """ActivityResult has expected fields."""
        result = ActivityResult(
            id=123,
            activity_type=ActivityType.STEP_COMPLETE,
            activity_date=date(2026, 1, 17),
            reference_id="phase0-topic1",
            created_at=datetime(2026, 1, 17, 10, 30, tzinfo=UTC),
        )
        assert result.id == 123
        assert result.activity_type == ActivityType.STEP_COMPLETE
        assert result.reference_id == "phase0-topic1"


class TestGetStreakData:
    """Tests for get_streak_data function."""

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_no_activities_returns_zeros(self):
        """User with no activities gets zero streak."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_activity_dates_ordered.return_value = []

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_streak_data(mock_db, "user-123")

        assert result.current_streak == 0
        assert result.longest_streak == 0
        assert result.total_activity_days == 0
        assert result.last_activity_date is None
        assert result.streak_alive is False

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_activity_today_has_streak(self):
        """User with activity today has a streak."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_activity_dates_ordered.return_value = [date(2026, 1, 17)]

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_streak_data(mock_db, "user-123")

        assert result.current_streak == 1
        assert result.streak_alive is True
        assert result.last_activity_date == date(2026, 1, 17)

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_consecutive_days_streak(self):
        """Multiple consecutive days counted correctly."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        # 5 consecutive days
        mock_repo.get_activity_dates_ordered.return_value = [
            date(2026, 1, 17),
            date(2026, 1, 16),
            date(2026, 1, 15),
            date(2026, 1, 14),
            date(2026, 1, 13),
        ]

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_streak_data(mock_db, "user-123")

        assert result.current_streak == 5
        assert result.longest_streak == 5
        assert result.total_activity_days == 5

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_duplicate_dates_deduplicated(self):
        """Multiple activities on same day count as one day."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        # Same date appears multiple times (multiple activities)
        mock_repo.get_activity_dates_ordered.return_value = [
            date(2026, 1, 17),
            date(2026, 1, 17),
            date(2026, 1, 16),
        ]

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_streak_data(mock_db, "user-123")

        assert result.total_activity_days == 2  # Only 2 unique days

    @pytest.mark.asyncio
    async def test_queries_limited_dates(self):
        """Repository query is limited to 100 dates for performance."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_activity_dates_ordered.return_value = []

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            await get_streak_data(mock_db, "user-123")

        # Verify limit=100 was passed
        mock_repo.get_activity_dates_ordered.assert_called_once_with(
            "user-123", limit=100
        )


class TestGetHeatmapData:
    """Tests for get_heatmap_data function."""

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_empty_heatmap(self):
        """User with no activities gets empty heatmap."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_heatmap_data.return_value = []

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_heatmap_data(mock_db, "user-123")

        assert result.days == []
        assert result.total_activities == 0
        assert result.end_date == date(2026, 1, 17)

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_heatmap_with_activities(self):
        """Heatmap aggregates activities by date."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        # Simulate: 2 step completions and 1 question passed on Jan 17
        mock_repo.get_heatmap_data.return_value = [
            (date(2026, 1, 17), "step_completed", 2),
            (date(2026, 1, 17), "question_passed", 1),
            (date(2026, 1, 16), "step_completed", 3),
        ]

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_heatmap_data(mock_db, "user-123")

        assert result.total_activities == 6  # 2+1+3
        assert len(result.days) == 2  # 2 unique days

        # Find Jan 17 data
        jan17 = next(d for d in result.days if d.date == date(2026, 1, 17))
        assert jan17.count == 3  # 2+1
        assert "step_completed" in jan17.activity_types
        assert "question_passed" in jan17.activity_types

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_heatmap_default_days(self):
        """Default heatmap is 365 days."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_heatmap_data.return_value = []

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_heatmap_data(mock_db, "user-123")

        assert result.start_date == date(2025, 1, 17)  # 365 days ago
        mock_repo.get_heatmap_data.assert_called_once()

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_heatmap_custom_days(self):
        """Heatmap can use custom day range."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_heatmap_data.return_value = []

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await get_heatmap_data(mock_db, "user-123", days=30)

        assert result.start_date == date(2025, 12, 18)  # 30 days ago


class TestLogActivity:
    """Tests for log_activity function."""

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17 10:30:00", tick=False)
    async def test_logs_activity_with_reference(self):
        """Activity logged with reference ID."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()

        # Mock the returned activity
        mock_activity = MagicMock()
        mock_activity.id = 456
        mock_activity.activity_type = ActivityType.STEP_COMPLETE
        mock_activity.activity_date = date(2026, 1, 17)
        mock_activity.reference_id = "phase0-topic1"
        mock_activity.created_at = datetime(2026, 1, 17, 10, 30, tzinfo=UTC)
        mock_repo.log_activity.return_value = mock_activity

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await log_activity(
                mock_db,
                "user-123",
                ActivityType.STEP_COMPLETE,
                reference_id="phase0-topic1",
            )

        assert result.id == 456
        assert result.activity_type == ActivityType.STEP_COMPLETE
        assert result.reference_id == "phase0-topic1"

        # Verify repo was called correctly
        mock_repo.log_activity.assert_called_once_with(
            user_id="user-123",
            activity_type=ActivityType.STEP_COMPLETE,
            activity_date=date(2026, 1, 17),
            reference_id="phase0-topic1",
        )

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_logs_activity_without_reference(self):
        """Activity logged without reference ID."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()

        mock_activity = MagicMock()
        mock_activity.id = 789
        mock_activity.activity_type = ActivityType.QUESTION_ATTEMPT
        mock_activity.activity_date = date(2026, 1, 17)
        mock_activity.reference_id = None
        mock_activity.created_at = datetime.now(UTC)
        mock_repo.log_activity.return_value = mock_activity

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            result = await log_activity(
                mock_db,
                "user-123",
                ActivityType.QUESTION_ATTEMPT,
            )

        assert result.reference_id is None
        mock_repo.log_activity.assert_called_once_with(
            user_id="user-123",
            activity_type=ActivityType.QUESTION_ATTEMPT,
            activity_date=date(2026, 1, 17),
            reference_id=None,
        )

    @pytest.mark.asyncio
    @time_machine.travel("2026-01-17")
    async def test_uses_utc_date(self):
        """Activity uses UTC date, not local date."""
        mock_db = MagicMock()
        mock_repo = AsyncMock()

        mock_activity = MagicMock()
        mock_activity.id = 1
        mock_activity.activity_type = ActivityType.STEP_COMPLETE
        mock_activity.activity_date = date(2026, 1, 17)
        mock_activity.reference_id = None
        mock_activity.created_at = datetime.now(UTC)
        mock_repo.log_activity.return_value = mock_activity

        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "services.activity_service.ActivityRepository",
                lambda db: mock_repo,
            )
            await log_activity(mock_db, "user-123", ActivityType.STEP_COMPLETE)

        # The date should be the UTC date
        call_kwargs = mock_repo.log_activity.call_args.kwargs
        assert call_kwargs["activity_date"] == date(2026, 1, 17)
