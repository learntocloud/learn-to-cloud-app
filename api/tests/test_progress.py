"""Tests for progress calculation.

Source of truth: .github/skills/progression-system/SKILL.md

Key rules from SKILL.md:
- Phase Progress = (Steps + Questions + Hands-on) / (Total Steps + Questions + Hands-on)
- Topic Progress = (Steps Completed + Questions Passed) / (Total Steps + Questions)
- Phase is complete when ALL: steps + questions + hands-on are done
- 7 total phases (0-6)
"""

import pytest

from services.progress import (
    PHASE_REQUIREMENTS,
    TOTAL_PHASES,
    TOTAL_QUESTIONS,
    TOTAL_STEPS,
    PhaseProgress,
    PhaseRequirements,
    UserProgress,
    get_all_phase_ids,
    get_phase_requirements,
)


class TestPhaseRequirementsMatchSkillMd:
    """Verify constants match SKILL.md source of truth."""

    def test_total_phases_is_7(self):
        """SKILL.md: Phases (7 total: 0-6)."""
        assert TOTAL_PHASES == 7

    def test_phase_ids_are_0_to_6(self):
        """SKILL.md: Phase IDs are 0-6."""
        assert get_all_phase_ids() == [0, 1, 2, 3, 4, 5, 6]

    def test_all_phases_have_requirements(self):
        """Each phase should have requirements defined."""
        for phase_id in range(7):
            req = get_phase_requirements(phase_id)
            assert req is not None
            assert req.phase_id == phase_id
            assert req.steps > 0
            assert req.questions > 0


class TestPhaseRequirementsTable:
    """Test requirements match SKILL.md table exactly."""

    def test_phase_requirements_table(self):
        """SKILL.md Phase Requirements table:

        | Phase | Steps | Questions | Hands-on |
        |-------|-------|-----------|----------|
        | 0     | 15    | 12        | 1        |
        | 1     | 36    | 12        | 3        |
        | 2     | 30    | 12        | 2        |
        | 3     | 31    | 8         | 1        |
        | 4     | 51    | 18        | 1        |
        | 5     | 55    | 12        | 4        |
        | 6     | 64    | 12        | 1        |
        """
        expected = {
            0: (15, 12),
            1: (36, 12),
            2: (30, 12),
            3: (31, 8),
            4: (51, 18),
            5: (55, 12),
            6: (64, 12),
        }
        for phase_id, (steps, questions) in expected.items():
            req = PHASE_REQUIREMENTS[phase_id]
            assert req.steps == steps, f"Phase {phase_id} steps mismatch"
            assert req.questions == questions, f"Phase {phase_id} questions mismatch"

    def test_total_steps_calculation(self):
        """Total steps should be sum of all phase steps."""
        expected_total = 15 + 36 + 30 + 31 + 51 + 55 + 64
        assert TOTAL_STEPS == expected_total

    def test_total_questions_calculation(self):
        """Total questions should be sum of all phase questions."""
        expected_total = 12 + 12 + 12 + 8 + 18 + 12 + 12
        assert TOTAL_QUESTIONS == expected_total


class TestPhaseProgressIsComplete:
    """Test PhaseProgress.is_complete property.

    SKILL.md: A Phase is Complete when ALL three requirements are met:
    1. All Learning Steps completed
    2. All Knowledge Questions passed
    3. All Hands-on Requirements validated
    """

    def test_incomplete_with_zero_progress(self):
        """Zero progress = not complete."""
        progress = PhaseProgress(
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
        assert progress.is_complete is False

    def test_incomplete_missing_steps(self):
        """Missing steps = not complete."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=10,  # Only 10/15
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert progress.is_complete is False

    def test_incomplete_missing_questions(self):
        """Missing questions = not complete."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=8,  # Only 8/12
            questions_required=12,
            hands_on_validated_count=1,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert progress.is_complete is False

    def test_incomplete_missing_hands_on(self):
        """Missing hands-on = not complete."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,  # Not validated
            hands_on_required=True,
        )
        assert progress.is_complete is False

    def test_complete_with_all_requirements(self):
        """All requirements met = complete."""
        progress = PhaseProgress(
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
        assert progress.is_complete is True

    def test_complete_with_no_hands_on_required(self):
        """Phase with no hands-on requirements."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=15,
            steps_required=15,
            questions_passed=12,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=0,
            hands_on_validated=True,  # No requirements = validated
            hands_on_required=False,
        )
        assert progress.is_complete is True


class TestPhaseProgressPercentage:
    """Test PhaseProgress.overall_percentage property.

    SKILL.md Phase Progress formula:
    (Steps + Questions + Hands-on) / (Total Steps + Questions + Hands-on)
    """

    def test_zero_progress_zero_percentage(self):
        """No progress = 0%."""
        progress = PhaseProgress(
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
        assert progress.overall_percentage == 0.0

    def test_full_progress_100_percentage(self):
        """Full progress = 100%."""
        progress = PhaseProgress(
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
        assert progress.overall_percentage == 100.0

    def test_partial_progress_calculation(self):
        """SKILL.md formula: (Steps + Questions + Hands-on) / Total.

        Phase 0: 15 steps, 12 questions, 1 hands-on = 28 total
        If: 10 steps + 6 questions + 0 hands-on = 16 completed
        Percentage = 16/28 * 100 = 57.14%
        """
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=10,
            steps_required=15,
            questions_passed=6,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        expected = (10 + 6 + 0) / (15 + 12 + 1) * 100
        assert progress.overall_percentage == pytest.approx(expected, rel=0.01)

    def test_over_completion_capped_at_100(self):
        """Exceeding requirements should still cap at 100%."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=20,  # More than required
            steps_required=15,
            questions_passed=15,  # More than required
            questions_required=12,
            hands_on_validated_count=2,  # More than required
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert progress.overall_percentage == 100.0

    def test_step_percentage_calculation(self):
        """Test step_percentage property."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=10,
            steps_required=15,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        expected = (10 / 15) * 100
        assert progress.step_percentage == pytest.approx(expected, rel=0.01)

    def test_question_percentage_calculation(self):
        """Test question_percentage property."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=0,
            steps_required=15,
            questions_passed=6,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )
        expected = (6 / 12) * 100
        assert progress.question_percentage == pytest.approx(expected, rel=0.01)

    def test_hands_on_percentage_calculation(self):
        """Test hands_on_percentage property."""
        progress = PhaseProgress(
            phase_id=5,  # Phase 5 has 4 hands-on requirements
            steps_completed=0,
            steps_required=55,
            questions_passed=0,
            questions_required=12,
            hands_on_validated_count=2,
            hands_on_required_count=4,
            hands_on_validated=False,
            hands_on_required=True,
        )
        expected = (2 / 4) * 100
        assert progress.hands_on_percentage == pytest.approx(expected, rel=0.01)


class TestUserProgress:
    """Test UserProgress class."""

    def test_phases_completed_count(self):
        """Count completed phases correctly."""
        phases = {
            0: PhaseProgress(0, 15, 15, 12, 12, 1, 1, True, True),
            1: PhaseProgress(1, 36, 36, 12, 12, 3, 3, True, True),
            2: PhaseProgress(2, 10, 30, 6, 12, 0, 2, False, True),  # Incomplete
        }
        progress = UserProgress(user_id="test", phases=phases)

        assert progress.phases_completed == 2

    def test_total_phases_constant(self):
        """total_phases should always be 7."""
        phases = {}
        progress = UserProgress(user_id="test", phases=phases)

        assert progress.total_phases == 7

    def test_current_phase_first_incomplete(self):
        """current_phase should be first incomplete phase."""
        phases = {
            0: PhaseProgress(0, 15, 15, 12, 12, 1, 1, True, True),  # Complete
            1: PhaseProgress(1, 36, 36, 12, 12, 3, 3, True, True),  # Complete
            2: PhaseProgress(2, 10, 30, 6, 12, 0, 2, False, True),  # Incomplete
            3: PhaseProgress(3, 0, 31, 0, 8, 0, 1, False, True),  # Incomplete
        }
        progress = UserProgress(user_id="test", phases=phases)

        assert progress.current_phase == 2

    def test_current_phase_when_all_complete(self):
        """current_phase should be last phase when all complete."""
        phases = {
            i: PhaseProgress(
                i,
                PHASE_REQUIREMENTS[i].steps,
                PHASE_REQUIREMENTS[i].steps,
                PHASE_REQUIREMENTS[i].questions,
                PHASE_REQUIREMENTS[i].questions,
                1,
                1,
                True,
                True,
            )
            for i in range(7)
        }
        progress = UserProgress(user_id="test", phases=phases)

        assert progress.current_phase == 6
        assert progress.is_program_complete is True

    def test_is_program_complete_false(self):
        """Program incomplete if any phase incomplete."""
        phases = {
            0: PhaseProgress(0, 15, 15, 12, 12, 1, 1, True, True),
            1: PhaseProgress(1, 10, 36, 6, 12, 0, 3, False, True),  # Incomplete
        }
        progress = UserProgress(user_id="test", phases=phases)

        assert progress.is_program_complete is False

    def test_overall_percentage_calculation(self):
        """Test overall percentage across all phases."""
        phases = {
            0: PhaseProgress(0, 15, 15, 12, 12, 1, 1, True, True),  # 100%
            1: PhaseProgress(1, 0, 36, 0, 12, 0, 3, False, True),  # 0%
        }
        progress = UserProgress(user_id="test", phases=phases)

        # Total: (15+12+1) + (36+12+3) = 28 + 51 = 79
        # Completed: (15+12+1) + (0+0+0) = 28
        # Percentage: 28/79 * 100 = 35.44%
        expected = (15 + 12 + 1) / (15 + 12 + 1 + 36 + 12 + 3) * 100
        assert progress.overall_percentage == pytest.approx(expected, rel=0.01)


class TestPhaseRequirementsDataclass:
    """Test PhaseRequirements dataclass."""

    def test_questions_per_topic_is_2(self):
        """SKILL.md implies 2 questions per topic."""
        req = PhaseRequirements(
            phase_id=0,
            name="Test",
            topics=6,
            steps=15,
            questions=12,
        )
        assert req.questions_per_topic == 2

    def test_phase_requirements_have_names(self):
        """Each phase should have a descriptive name."""
        expected_names = {
            0: "IT Fundamentals & Cloud Overview",
            1: "Linux, CLI & Version Control",
            2: "Programming & APIs",
            3: "AI & Productivity",
            4: "Cloud Deployment",
            5: "DevOps & Containers",
            6: "Cloud Security",
        }
        for phase_id, expected_name in expected_names.items():
            assert PHASE_REQUIREMENTS[phase_id].name == expected_name
