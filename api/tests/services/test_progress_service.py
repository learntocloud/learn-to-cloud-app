"""Unit tests for progress_service.

Tests cover:
- compute_topic_progress status derivation and stale-step filtering
- phase_progress_to_data status mapping
- fetch_user_progress cache hit/miss and DB assembly
- get_phase_detail_progress cache hit/miss and per-topic breakdown
"""

from unittest.mock import AsyncMock, patch

import pytest

from schemas import (
    LearningStep,
    Phase,
    PhaseProgress,
    Topic,
    UserProgress,
)
from services.progress_service import (
    _build_phase_requirements,
    compute_topic_progress,
    fetch_user_progress,
    get_phase_detail_progress,
    phase_progress_to_data,
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
    step_ids = steps if steps is not None else ["s1", "s2", "s3"]
    return Topic(
        id=topic_id,
        slug="topic1",
        name="Test Topic",
        description="A test topic",
        order=0,
        learning_steps=[_make_step(sid, i) for i, sid in enumerate(step_ids)],
    )


def _make_phase(
    phase_id: int = 0,
    topics: list[Topic] | None = None,
) -> Phase:
    return Phase(
        id=phase_id,
        name=f"Phase {phase_id}",
        slug=f"phase{phase_id}",
        order=phase_id,
        topics=topics or [],
    )


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """Clear lru_cache between tests to prevent leakage."""
    yield
    _build_phase_requirements.cache_clear()


# ---------------------------------------------------------------------------
# compute_topic_progress (pure function — no mocking needed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeTopicProgress:
    def test_no_steps_completed(self):
        topic = _make_topic(steps=["s1", "s2", "s3"])
        result = compute_topic_progress(topic, set())
        assert result.status == "not_started"
        assert result.percentage == 0.0
        assert result.steps_completed == 0
        assert result.steps_total == 3

    def test_partial_progress(self):
        topic = _make_topic(steps=["s1", "s2", "s3"])
        result = compute_topic_progress(topic, {"s1"})
        assert result.status == "in_progress"
        assert result.percentage == pytest.approx(33.3, abs=0.1)
        assert result.steps_completed == 1

    def test_all_steps_completed(self):
        topic = _make_topic(steps=["s1", "s2"])
        result = compute_topic_progress(topic, {"s1", "s2"})
        assert result.status == "completed"
        assert result.percentage == 100.0

    def test_stale_step_ids_filtered(self):
        topic = _make_topic(steps=["s1", "s2"])
        result = compute_topic_progress(topic, {"s1", "s3_stale"})
        assert result.steps_completed == 1
        assert result.percentage == 50.0

    def test_zero_step_topic(self):
        topic = _make_topic(steps=[])
        result = compute_topic_progress(topic, set())
        assert result.status == "completed"
        assert result.percentage == 100.0

    def test_superset_of_steps_caps_at_total(self):
        topic = _make_topic(steps=["s1"])
        result = compute_topic_progress(topic, {"s1"})
        assert result.steps_completed == 1
        assert result.steps_total == 1


# ---------------------------------------------------------------------------
# phase_progress_to_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseProgressToData:
    def test_completed_status(self):
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=5,
            steps_required=5,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "completed"

    def test_in_progress_from_steps(self):
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=2,
            steps_required=5,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "in_progress"

    def test_in_progress_from_hands_on_only(self):
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=5,
            hands_on_validated_count=1,
            hands_on_required_count=2,
            hands_on_validated=False,
            hands_on_required=True,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "in_progress"

    def test_not_started(self):
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=5,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        data = phase_progress_to_data(progress)
        assert data.status == "not_started"


# ---------------------------------------------------------------------------
# fetch_user_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchUserProgress:
    @pytest.mark.asyncio
    async def test_returns_cached_value(self):
        cached = UserProgress(user_id=1, phases={}, total_phases=0)
        with patch(
            "services.progress_service.get_cached_progress",
            autospec=True,
            return_value=cached,
        ):
            result = await fetch_user_progress(AsyncMock(), user_id=1)
        assert result is cached

    @pytest.mark.asyncio
    async def test_skip_cache_bypasses_cache(self):
        topic = _make_topic(steps=["s1"])
        phase = _make_phase(0, topics=[topic])

        with (
            patch(
                "services.progress_service.get_cached_progress",
                autospec=True,
                return_value=UserProgress(user_id=1, phases={}, total_phases=0),
            ) as mock_cache,
            patch(
                "services.progress_service.get_all_phases",
                autospec=True,
                return_value=(phase,),
            ),
            patch(
                "services.progress_service.UserPhaseProgressRepository",
                autospec=True,
            ) as MockDenorm,
            patch(
                "services.progress_service.StepProgressRepository",
                autospec=True,
            ) as MockStepRepo,
            patch(
                "services.progress_service.get_requirements_for_phase",
                autospec=True,
                return_value=[],
            ),
            patch(
                "services.progress_service.set_cached_progress",
                autospec=True,
            ),
        ):
            MockDenorm.return_value.get_by_user = AsyncMock(return_value={})
            MockStepRepo.return_value.get_completed_for_topics = AsyncMock(
                return_value={}
            )
            result = await fetch_user_progress(AsyncMock(), user_id=1, skip_cache=True)
            mock_cache.assert_not_called()
            assert result.user_id == 1


# ---------------------------------------------------------------------------
# get_phase_detail_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPhaseDetailProgress:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        topic = _make_topic(steps=["s1", "s2"])
        phase = _make_phase(0, topics=[topic])
        cached_data = {"phase0-topic1": {"s1"}}

        with (
            patch(
                "services.progress_service.get_cached_phase_detail",
                autospec=True,
                return_value=cached_data,
            ),
            patch(
                "services.progress_service.get_requirements_for_phase",
                autospec=True,
                return_value=[],
            ),
        ):
            result = await get_phase_detail_progress(
                AsyncMock(), user_id=1, phase=phase
            )

        assert result.steps_completed == 1
        assert result.steps_total == 2
        assert result.percentage == 50

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        topic = _make_topic(steps=["s1", "s2"])
        phase = _make_phase(0, topics=[topic])

        with (
            patch(
                "services.progress_service.get_cached_phase_detail",
                autospec=True,
                return_value=None,
            ),
            patch(
                "services.progress_service.StepProgressRepository",
                autospec=True,
            ) as MockStepRepo,
            patch(
                "services.progress_service.set_cached_phase_detail",
                autospec=True,
            ) as mock_set_cache,
            patch(
                "services.progress_service.get_requirements_for_phase",
                autospec=True,
                return_value=[],
            ),
        ):
            MockStepRepo.return_value.get_completed_for_topics = AsyncMock(
                return_value={"phase0-topic1": {"s1", "s2"}}
            )
            result = await get_phase_detail_progress(
                AsyncMock(), user_id=1, phase=phase
            )

        assert result.steps_completed == 2
        assert result.percentage == 100
        mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_percentage_includes_hands_on(self):
        """All steps done but hands-on incomplete → not 100%."""
        topic = _make_topic(topic_id="phase3-topic1", steps=["s1", "s2"])
        phase = _make_phase(3, topics=[topic])
        cached_data = {"phase3-topic1": {"s1", "s2"}}

        mock_req = type("Req", (), {"id": "req1"})()

        mock_row = type("Row", (), {"validated_submissions": 0})()

        with (
            patch(
                "services.progress_service.get_cached_phase_detail",
                autospec=True,
                return_value=cached_data,
            ),
            patch(
                "services.progress_service.get_requirements_for_phase",
                autospec=True,
                return_value=[mock_req],
            ),
            patch(
                "services.progress_service.UserPhaseProgressRepository",
                autospec=True,
            ) as MockProgressRepo,
        ):
            MockProgressRepo.return_value.get_by_user = AsyncMock(
                return_value={3: mock_row}
            )
            result = await get_phase_detail_progress(
                AsyncMock(), user_id=1, phase=phase
            )

        # 2 steps done + 0 hands-on out of 2 steps + 1 hands-on = 2/3 ≈ 67%
        assert result.steps_completed == 2
        assert result.hands_on_validated == 0
        assert result.hands_on_required == 1
        assert result.percentage == 67
