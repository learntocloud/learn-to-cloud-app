"""Unit tests for services/progress.py.

Tests PhaseProgress and UserProgress dataclasses following the progression
system specification from api/docs/progression-system.md.

Total test cases: 66
- TestPhaseProgressIsComplete: 11 tests
- TestPhaseProgressOverallPercentage: 8 tests
- TestPhaseProgressHandsOnPercentage: 5 tests
- TestUserProgressProperties: 9 tests
- TestPhaseProgressPropertyBased: 2 Hypothesis tests
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from services.progress_service import (
    PHASE_REQUIREMENTS,
    PhaseProgress,
)


class TestPhaseProgressIsComplete:
    """Test PhaseProgress.is_complete property.

    Per spec: Phase is complete when ALL three requirements are met:
    - All steps completed
    - All questions passed
    - All hands-on validated (if required)
    """

    def test_complete_with_all_requirements_met(self):
        """Phase complete when steps + questions + hands-on all met."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.is_complete is True

    def test_incomplete_missing_steps(self):
        """Phase incomplete when missing steps."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=10,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.is_complete is False

    def test_incomplete_missing_questions(self):
        """Phase incomplete when missing questions."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=8,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.is_complete is False

    def test_incomplete_missing_hands_on(self):
        """Phase incomplete when missing hands-on validation."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        assert phase.is_complete is False

    def test_complete_with_no_hands_on_required(self):
        """Phase complete when no hands-on required and steps/questions done."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=0,
            hands_on_validated=True,
            hands_on_required=False,
        )
        assert phase.is_complete is True

    def test_incomplete_with_zero_progress(self):
        """Phase incomplete with zero progress."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=15,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        assert phase.is_complete is False

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_complete_for_all_phases(self, phase_id):
        """Phase complete works for all 7 phases when requirements met."""
        from services.phase_requirements_service import get_requirements_for_phase

        req = PHASE_REQUIREMENTS[phase_id]
        hands_on_count = len(get_requirements_for_phase(phase_id))

        phase = PhaseProgress(
            phase_id=phase_id,
            steps_completed=req.steps,
            steps_required=req.steps,
            questions_passed=req.questions,
            questions_required=req.questions,
            hands_on_validated_count=hands_on_count,
            hands_on_required_count=hands_on_count,
            hands_on_validated=True,
            hands_on_required=hands_on_count > 0,
        )
        assert phase.is_complete is True

    def test_allows_extra_progress_steps(self):
        """Phase complete even with extra steps completed."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=20,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.is_complete is True

    def test_allows_extra_progress_questions(self):
        """Phase complete even with extra questions passed."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=15,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.is_complete is True

    def test_allows_extra_progress_hands_on(self):
        """Phase complete even with extra hands-on validated."""
        phase = PhaseProgress(
            phase_id=1,
            steps_completed=36,
            steps_required=36,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=5,
            hands_on_required_count=3,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.is_complete is True

    def test_incomplete_only_hands_on_missing(self):
        """Phase incomplete when only hands-on missing."""
        phase = PhaseProgress(
            phase_id=5,
            steps_completed=55,
            steps_required=55,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=2,
            hands_on_required_count=4,
            hands_on_validated=False,
            hands_on_required=True,
        )
        assert phase.is_complete is False


class TestPhaseProgressOverallPercentage:
    """Test PhaseProgress.overall_percentage property.

    Per spec: Percentage = (Completed Steps + Passed Questions + Validated Hands-on) /
                           (Total Steps + Questions + Hands-on) * 100
    """

    def test_zero_progress_returns_zero_percent(self):
        """Zero progress returns 0%."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=15,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        assert phase.overall_percentage == 0.0

    def test_complete_progress_returns_100_percent(self):
        """Complete progress returns 100%."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.overall_percentage == 100.0

    def test_half_progress_correct_percentage(self):
        """Half progress returns correct percentage."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=7,
            steps_required=15,
            questions_passed=6,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        # (7 + 6 + 0) / (15 + 12 + 1) = 13 / 28 = 46.43%
        expected = (13 / 28) * 100
        assert abs(phase.overall_percentage - expected) < 0.01

    def test_only_steps_completed(self):
        """Only steps completed returns correct percentage."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        # (15 + 0 + 0) / (15 + 12 + 1) = 15 / 28 = 53.57%
        expected = (15 / 28) * 100
        assert abs(phase.overall_percentage - expected) < 0.01

    def test_only_questions_completed(self):
        """Only questions completed returns correct percentage."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        # (0 + 12 + 0) / (15 + 12 + 1) = 12 / 28 = 42.86%
        expected = (12 / 28) * 100
        assert abs(phase.overall_percentage - expected) < 0.01

    def test_only_hands_on_completed(self):
        """Only hands-on completed returns correct percentage."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=15,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        # (0 + 0 + 1) / (15 + 12 + 1) = 1 / 28 = 3.57%
        expected = (1 / 28) * 100
        assert abs(phase.overall_percentage - expected) < 0.01

    def test_phase_with_no_requirements_returns_zero(self):
        """Phase with no requirements returns 0%."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=0,
            questions_passed=0,
            questions_required=0,
            hands_on_validated_count=0,
            hands_on_required_count=0,
            hands_on_validated=True,
            hands_on_required=False,
        )
        assert phase.overall_percentage == 0.0

    def test_percentage_capped_at_100(self):
        """Percentage is capped at 100% even with extra progress."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=20,
            steps_required=15,
            questions_passed=15,
            questions_required=12,
            hands_on_validated_count=2,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        # Capping: min(20, 15) + min(15, 12) + min(2, 1) = 15 + 12 + 1 = 28
        # (28) / (28) = 100%
        assert phase.overall_percentage == 100.0


class TestPhaseProgressHandsOnPercentage:
    """Test PhaseProgress.hands_on_percentage property."""

    def test_zero_hands_on_validated(self):
        """Zero hands-on validated returns 0%."""
        phase = PhaseProgress(
            phase_id=1,
            steps_completed=0,
            steps_required=36,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=3,
            hands_on_validated=False,
            hands_on_required=True,
        )
        assert phase.hands_on_percentage == 0.0

    def test_all_hands_on_validated(self):
        """All hands-on validated returns 100%."""
        phase = PhaseProgress(
            phase_id=1,
            steps_completed=36,
            steps_required=36,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=3,
            hands_on_required_count=3,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.hands_on_percentage == 100.0

    def test_partial_hands_on_validated(self):
        """Partial hands-on validated returns correct percentage."""
        phase = PhaseProgress(
            phase_id=5,
            steps_completed=0,
            steps_required=55,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=2,
            hands_on_required_count=4,
            hands_on_validated=False,
            hands_on_required=True,
        )
        # (2 / 4) * 100 = 50%
        assert phase.hands_on_percentage == 50.0

    def test_no_hands_on_required_returns_100(self):
        """No hands-on required returns 100%."""
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=0,
            hands_on_validated=True,
            hands_on_required=False,
        )
        assert phase.hands_on_percentage == 100.0

    def test_hands_on_percentage_capped_at_100(self):
        """Hands-on percentage is capped at 100%."""
        phase = PhaseProgress(
            phase_id=1,
            steps_completed=36,
            steps_required=36,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=5,
            hands_on_required_count=3,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert phase.hands_on_percentage == 100.0


class TestUserProgressProperties:
    """Test UserProgress properties."""

    def test_phases_completed_with_no_progress(self, empty_user_progress):
        """User with no progress has 0 phases completed."""
        assert empty_user_progress.phases_completed == 0

    def test_phases_completed_with_all_progress(self, completed_user_progress):
        """User with all phases complete has 7 phases completed."""
        assert completed_user_progress.phases_completed == 7

    def test_total_phases_is_seven(self, empty_user_progress):
        """Total phases is always 7."""
        assert empty_user_progress.total_phases == 7

    def test_current_phase_for_new_user(self, empty_user_progress):
        """New user's current phase is 0."""
        assert empty_user_progress.current_phase == 0

    def test_current_phase_for_completed_user(self, completed_user_progress):
        """Completed user's current phase is 6 (last phase)."""
        assert completed_user_progress.current_phase == 6

    def test_current_phase_for_mid_program_user(self, mid_program_user_progress):
        """Mid-program user's current phase is first incomplete."""
        assert mid_program_user_progress.current_phase == 1

    def test_is_program_complete_false(self, empty_user_progress):
        """Program not complete when not all phases done."""
        assert empty_user_progress.is_program_complete is False

    def test_is_program_complete_true(self, completed_user_progress):
        """Program complete when all phases done."""
        assert completed_user_progress.is_program_complete is True

    def test_overall_percentage_for_new_user(self, empty_user_progress):
        """New user has 0% overall progress."""
        assert empty_user_progress.overall_percentage == 0.0

    def test_overall_percentage_for_completed_user(self, completed_user_progress):
        """Completed user has 100% overall progress."""
        assert completed_user_progress.overall_percentage == 100.0


class TestPhaseProgressPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(
        steps_completed=st.integers(min_value=0, max_value=100),
        steps_required=st.integers(min_value=1, max_value=100),
        questions_passed=st.integers(min_value=0, max_value=50),
        questions_required=st.integers(min_value=1, max_value=50),
        hands_on_validated_count=st.integers(min_value=0, max_value=10),
        hands_on_required_count=st.integers(min_value=0, max_value=10),
    )
    def test_overall_percentage_never_exceeds_100(
        self,
        steps_completed,
        steps_required,
        questions_passed,
        questions_required,
        hands_on_validated_count,
        hands_on_required_count,
    ):
        """Overall percentage should never exceed 100% regardless of inputs."""
        hands_on_validated = hands_on_validated_count >= hands_on_required_count
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=steps_completed,
            steps_required=steps_required,
            questions_passed=questions_passed,
            questions_required=questions_required,
            hands_on_validated_count=hands_on_validated_count,
            hands_on_required_count=hands_on_required_count,
            hands_on_validated=hands_on_validated,
            hands_on_required=hands_on_required_count > 0,
        )
        assert 0 <= phase.overall_percentage <= 100

    @given(
        steps_completed=st.integers(min_value=0, max_value=100),
        steps_required=st.integers(min_value=1, max_value=100),
        questions_passed=st.integers(min_value=0, max_value=50),
        questions_required=st.integers(min_value=1, max_value=50),
        hands_on_validated_count=st.integers(min_value=0, max_value=10),
        hands_on_required_count=st.integers(min_value=1, max_value=10),
    )
    def test_is_complete_requires_all_three(
        self,
        steps_completed,
        steps_required,
        questions_passed,
        questions_required,
        hands_on_validated_count,
        hands_on_required_count,
    ):
        """Phase completion requires all three: steps AND questions AND hands-on."""
        hands_on_validated = hands_on_validated_count >= hands_on_required_count
        phase = PhaseProgress(
            phase_id=0,
            steps_completed=steps_completed,
            steps_required=steps_required,
            questions_passed=questions_passed,
            questions_required=questions_required,
            hands_on_validated_count=hands_on_validated_count,
            hands_on_required_count=hands_on_required_count,
            hands_on_validated=hands_on_validated,
            hands_on_required=True,
        )

        if phase.is_complete:
            assert steps_completed >= steps_required
            assert questions_passed >= questions_required
            assert hands_on_validated is True
