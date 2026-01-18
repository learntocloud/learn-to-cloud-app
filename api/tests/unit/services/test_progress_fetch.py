"""Unit tests for fetch_user_progress and related async functions.

Tests the main entry point for getting user progress data with mocked
database queries and caching behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.progress_service import (
    PHASE_REQUIREMENTS,
    PhaseProgress,
    UserProgress,
    fetch_user_progress,
    get_all_phase_ids,
    get_phase_completion_counts,
    get_phase_requirements,
)


class TestGetPhaseRequirements:
    """Test get_phase_requirements helper function."""

    def test_valid_phase_returns_requirements(self):
        """Valid phase ID returns PhaseRequirements."""
        result = get_phase_requirements(0)
        assert result is not None
        assert result.phase_id == 0
        assert result.name == "IT Fundamentals & Cloud Overview"
        assert result.topics == 6
        assert result.steps == 15
        assert result.questions == 12

    def test_all_phases_have_requirements(self):
        """All phase IDs (0-6) return requirements."""
        for phase_id in range(7):
            result = get_phase_requirements(phase_id)
            assert result is not None
            assert result.phase_id == phase_id

    def test_invalid_phase_returns_none(self):
        """Invalid phase ID returns None."""
        assert get_phase_requirements(99) is None
        assert get_phase_requirements(-1) is None


class TestGetAllPhaseIds:
    """Test get_all_phase_ids helper function."""

    def test_returns_sorted_phase_ids(self):
        """Returns all phase IDs in sorted order."""
        result = get_all_phase_ids()
        assert result == [0, 1, 2, 3, 4, 5, 6]

    def test_returns_list(self):
        """Result is a list."""
        result = get_all_phase_ids()
        assert isinstance(result, list)


class TestFetchUserProgress:
    """Test fetch_user_progress async function."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock AsyncSession."""
        return MagicMock()

    @pytest.fixture
    def mock_repos(self):
        """Create mock repository instances."""
        with (
            patch("services.progress_service.QuestionAttemptRepository") as q_repo,
            patch("services.progress_service.StepProgressRepository") as s_repo,
            patch("services.progress_service.SubmissionRepository") as sub_repo,
        ):
            q_instance = AsyncMock()
            s_instance = AsyncMock()
            sub_instance = AsyncMock()

            q_repo.return_value = q_instance
            s_repo.return_value = s_instance
            sub_repo.return_value = sub_instance

            yield {
                "question_repo": q_instance,
                "step_repo": s_instance,
                "submission_repo": sub_instance,
            }

    @pytest.mark.asyncio
    async def test_fetch_progress_new_user(self, mock_db, mock_repos):
        """New user with no progress returns zeros for all phases."""
        mock_repos["question_repo"].get_all_passed_question_ids.return_value = []
        mock_repos["step_repo"].get_completed_step_topic_ids.return_value = []
        mock_repos["submission_repo"].get_validated_by_user.return_value = []

        with (
            patch("services.progress_service.get_cached_progress", return_value=None),
            patch("services.progress_service.set_cached_progress"),
            patch(
                "services.progress_service.get_requirements_for_phase", return_value=[]
            ),
        ):
            result = await fetch_user_progress(mock_db, "new-user")

        assert isinstance(result, UserProgress)
        assert result.user_id == "new-user"
        assert len(result.phases) == 7

        # All phases should have zero progress
        for phase_id, phase in result.phases.items():
            assert phase.steps_completed == 0
            assert phase.questions_passed == 0

    @pytest.mark.asyncio
    async def test_fetch_progress_uses_cache_when_available(self, mock_db):
        """Returns cached progress when available."""
        cached_progress = UserProgress(
            user_id="cached-user",
            phases={
                0: PhaseProgress(
                    phase_id=0,
                    steps_completed=5,
                    steps_required=15,
                    questions_passed=3,
                    questions_required=12,
                    hands_on_validated_count=0,
                    hands_on_required_count=0,
                    hands_on_validated=True,
                    hands_on_required=False,
                )
            },
        )

        with patch(
            "services.progress_service.get_cached_progress",
            return_value=cached_progress,
        ):
            result = await fetch_user_progress(mock_db, "cached-user")

        assert result is cached_progress
        assert result.phases[0].steps_completed == 5

    @pytest.mark.asyncio
    async def test_fetch_progress_skip_cache(self, mock_db, mock_repos):
        """skip_cache=True bypasses cache and queries DB."""
        mock_repos["question_repo"].get_all_passed_question_ids.return_value = []
        mock_repos["step_repo"].get_completed_step_topic_ids.return_value = []
        mock_repos["submission_repo"].get_validated_by_user.return_value = []

        with (
            patch("services.progress_service.get_cached_progress") as cache_get,
            patch("services.progress_service.set_cached_progress"),
            patch(
                "services.progress_service.get_requirements_for_phase", return_value=[]
            ),
        ):
            result = await fetch_user_progress(mock_db, "user-1", skip_cache=True)

        # Cache should not be checked when skip_cache=True
        cache_get.assert_not_called()
        assert result.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_fetch_progress_with_completed_steps(self, mock_db, mock_repos):
        """Progress reflects completed steps by phase."""
        mock_repos["question_repo"].get_all_passed_question_ids.return_value = []
        mock_repos["step_repo"].get_completed_step_topic_ids.return_value = [
            "phase0-topic1",
            "phase0-topic2",
            "phase1-topic1",
        ]
        mock_repos["submission_repo"].get_validated_by_user.return_value = []

        with (
            patch("services.progress_service.get_cached_progress", return_value=None),
            patch("services.progress_service.set_cached_progress"),
            patch(
                "services.progress_service.get_requirements_for_phase", return_value=[]
            ),
        ):
            result = await fetch_user_progress(mock_db, "user-1")

        assert result.phases[0].steps_completed == 2  # 2 in phase0
        assert result.phases[1].steps_completed == 1  # 1 in phase1
        assert result.phases[2].steps_completed == 0  # none in phase2

    @pytest.mark.asyncio
    async def test_fetch_progress_with_passed_questions(self, mock_db, mock_repos):
        """Progress reflects passed questions by phase."""
        mock_repos["question_repo"].get_all_passed_question_ids.return_value = [
            "phase0-topic1-q1",
            "phase0-topic1-q2",
            "phase0-topic2-q1",
            "phase2-topic1-q1",
        ]
        mock_repos["step_repo"].get_completed_step_topic_ids.return_value = []
        mock_repos["submission_repo"].get_validated_by_user.return_value = []

        with (
            patch("services.progress_service.get_cached_progress", return_value=None),
            patch("services.progress_service.set_cached_progress"),
            patch(
                "services.progress_service.get_requirements_for_phase", return_value=[]
            ),
        ):
            result = await fetch_user_progress(mock_db, "user-1")

        assert result.phases[0].questions_passed == 3  # 3 in phase0
        assert result.phases[2].questions_passed == 1  # 1 in phase2
        assert result.phases[1].questions_passed == 0  # none in phase1

    @pytest.mark.asyncio
    async def test_fetch_progress_caches_result(self, mock_db, mock_repos):
        """Result is cached after fetching from DB."""
        mock_repos["question_repo"].get_all_passed_question_ids.return_value = []
        mock_repos["step_repo"].get_completed_step_topic_ids.return_value = []
        mock_repos["submission_repo"].get_validated_by_user.return_value = []

        with (
            patch("services.progress_service.get_cached_progress", return_value=None),
            patch("services.progress_service.set_cached_progress") as cache_set,
            patch(
                "services.progress_service.get_requirements_for_phase", return_value=[]
            ),
        ):
            result = await fetch_user_progress(mock_db, "user-1")

        cache_set.assert_called_once_with("user-1", result)

    @pytest.mark.asyncio
    async def test_fetch_progress_with_hands_on_requirements(self, mock_db, mock_repos):
        """Progress reflects hands-on validation status."""
        mock_repos["question_repo"].get_all_passed_question_ids.return_value = []
        mock_repos["step_repo"].get_completed_step_topic_ids.return_value = []

        # Mock a validated submission for phase 4
        mock_submission = MagicMock()
        mock_submission.requirement_id = "req-1"
        mock_submission.phase_id = 4
        mock_repos["submission_repo"].get_validated_by_user.return_value = [
            mock_submission
        ]

        # Mock hands-on requirements
        mock_requirement = MagicMock()
        mock_requirement.id = "req-1"

        def get_reqs(phase_id):
            if phase_id == 4:
                return [mock_requirement]
            return []

        with (
            patch("services.progress_service.get_cached_progress", return_value=None),
            patch("services.progress_service.set_cached_progress"),
            patch(
                "services.progress_service.get_requirements_for_phase",
                side_effect=get_reqs,
            ),
            patch(
                "services.submissions_service.get_validated_ids_by_phase"
            ) as mock_validated,
        ):
            mock_validated.return_value = {4: {"req-1"}}
            result = await fetch_user_progress(mock_db, "user-1")

        # Phase 4 should have hands-on validated
        assert result.phases[4].hands_on_validated_count == 1
        assert result.phases[4].hands_on_required_count == 1
        assert result.phases[4].hands_on_validated is True


class TestGetPhaseCompletionCounts:
    """Test get_phase_completion_counts helper function."""

    def test_converts_progress_to_tuple_format(self):
        """Converts UserProgress to dict of tuples."""
        progress = UserProgress(
            user_id="test-user",
            phases={
                0: PhaseProgress(
                    phase_id=0,
                    steps_completed=15,
                    steps_required=15,
                    questions_passed=12,
                    questions_required=12,
                    hands_on_validated_count=1,
                    hands_on_required_count=1,
                    hands_on_validated=True,
                    hands_on_required=True,
                ),
                1: PhaseProgress(
                    phase_id=1,
                    steps_completed=20,
                    steps_required=36,
                    questions_passed=8,
                    questions_required=12,
                    hands_on_validated_count=0,
                    hands_on_required_count=2,
                    hands_on_validated=False,
                    hands_on_required=True,
                ),
            },
        )

        result = get_phase_completion_counts(progress)

        assert result[0] == (15, 12, True)  # (steps, questions, hands_on)
        assert result[1] == (20, 8, False)

    def test_empty_phases(self):
        """Empty phases returns empty dict."""
        progress = UserProgress(user_id="empty-user", phases={})
        result = get_phase_completion_counts(progress)
        assert result == {}


class TestPhaseRequirementsQuestionsPerTopic:
    """Test PhaseRequirements.questions_per_topic property."""

    def test_questions_per_topic_is_two(self):
        """Each topic has 2 questions per spec."""
        for phase_id, requirements in PHASE_REQUIREMENTS.items():
            # Verify questions = topics * 2
            assert requirements.questions == requirements.topics * 2


class TestUserProgressOverallPercentage:
    """Test UserProgress.overall_percentage property with edge cases."""

    def test_overall_percentage_empty_phases(self):
        """Empty phases returns 0%."""
        progress = UserProgress(user_id="empty", phases={})
        assert progress.overall_percentage == 0.0

    def test_overall_percentage_partial_completion(self):
        """Partial completion calculates correctly."""
        progress = UserProgress(
            user_id="partial",
            phases={
                0: PhaseProgress(
                    phase_id=0,
                    steps_completed=8,
                    steps_required=16,
                    questions_passed=6,
                    questions_required=12,
                    hands_on_validated_count=1,
                    hands_on_required_count=2,
                    hands_on_validated=False,
                    hands_on_required=True,
                ),
            },
        )
        # Total requirements: 16 steps + 12 questions + 2 hands-on = 30
        # Completed: 8 steps + 6 questions + 1 hands-on = 15
        # Percentage: 15/30 = 50%
        assert progress.overall_percentage == 50.0

    def test_overall_percentage_over_100_capped(self):
        """Over-completion is capped at required amounts."""
        progress = UserProgress(
            user_id="over",
            phases={
                0: PhaseProgress(
                    phase_id=0,
                    steps_completed=100,  # More than required
                    steps_required=10,
                    questions_passed=50,  # More than required
                    questions_required=10,
                    hands_on_validated_count=5,  # More than required
                    hands_on_required_count=2,
                    hands_on_validated=True,
                    hands_on_required=True,
                ),
            },
        )
        # Should be capped at 100% not higher
        assert progress.overall_percentage == 100.0
