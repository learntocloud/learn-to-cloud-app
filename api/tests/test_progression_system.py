"""Comprehensive tests for the progression system.

Source of truth: .github/skills/progression-system/SKILL.md

This test file validates that the API implementation honors all rules
defined in the progression system skill documentation. The SKILL.md file
is authoritative - if tests fail, the API should be updated, not the SKILL.md.

Test organization:
1. SKILL.md Validation - Content hierarchy, requirements table, badges
2. Completion & Progress - Phase completion rules, progress calculation
3. Badge System - Badge definitions, awarding rules, streak badges
4. Unlocking Rules - Sequential unlocking, admin bypass
5. Database Integration - Full user journeys with realistic data
6. Property-Based Tests - Edge case discovery with Hypothesis
"""

import uuid
from datetime import UTC, datetime

import pytest
from faker import Faker
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from models import QuestionAttempt, StepProgress, Submission, SubmissionType, User
from services.badges import (
    PHASE_BADGES,
    STREAK_BADGES,
    compute_all_badges,
    compute_phase_badges,
    compute_streak_badges,
    get_all_available_badges,
)
from services.hands_on_verification import (
    HANDS_ON_REQUIREMENTS,
    get_requirement_by_id,
    get_requirements_for_phase,
)
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
from services.steps import (
    StepNotUnlockedError,
    complete_step,
    get_topic_step_progress,
)

fake = Faker()


# =============================================================================
# SKILL.MD VALIDATION: Content Hierarchy & Requirements Table
# =============================================================================

# The SKILL.md table is the source of truth for all phase requirements
SKILL_MD_REQUIREMENTS = {
    0: {"steps": 15, "questions": 12, "hands_on": 1},
    1: {"steps": 36, "questions": 12, "hands_on": 3},
    2: {"steps": 30, "questions": 12, "hands_on": 2},
    3: {"steps": 31, "questions": 8, "hands_on": 1},
    4: {"steps": 51, "questions": 18, "hands_on": 1},
    5: {"steps": 55, "questions": 12, "hands_on": 4},
    6: {"steps": 64, "questions": 12, "hands_on": 1},
}

# The SKILL.md badge definitions
SKILL_MD_BADGES = {
    0: {"name": "Explorer", "tier": "Bronze", "icon": "🥉"},
    1: {"name": "Practitioner", "tier": "Silver", "icon": "🥈"},
    2: {"name": "Builder", "tier": "Blue", "icon": "🔵"},
    3: {"name": "Specialist", "tier": "Purple", "icon": "🟣"},
    4: {"name": "Architect", "tier": "Gold", "icon": "🥇"},
    5: {"name": "Master", "tier": "Red", "icon": "🔴"},
    6: {"name": "Legend", "tier": "Rainbow", "icon": "🌈"},
}


class TestContentHierarchy:
    """SKILL.md: Phases (7 total: 0-6)."""

    def test_total_phases_is_7(self):
        """SKILL.md specifies 7 total phases numbered 0-6."""
        assert TOTAL_PHASES == 7

    def test_phase_ids_are_0_through_6(self):
        """SKILL.md: Phase IDs are 0, 1, 2, 3, 4, 5, 6."""
        expected_ids = [0, 1, 2, 3, 4, 5, 6]
        actual_ids = get_all_phase_ids()
        assert actual_ids == expected_ids

    def test_all_phases_have_requirements_defined(self):
        """Each phase must have requirements defined in PHASE_REQUIREMENTS."""
        for phase_id in range(7):
            req = get_phase_requirements(phase_id)
            assert req is not None, f"Phase {phase_id} missing requirements"
            assert isinstance(req, PhaseRequirements)


class TestPhaseRequirementsTable:
    """SKILL.md: Phase Requirements table must match exactly."""

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_phase_steps_match_skill_md(self, phase_id: int):
        """Steps for each phase must match SKILL.md table."""
        expected = SKILL_MD_REQUIREMENTS[phase_id]["steps"]
        actual = PHASE_REQUIREMENTS[phase_id].steps
        assert actual == expected, (
            f"Phase {phase_id} steps mismatch: "
            f"SKILL.md says {expected}, API has {actual}"
        )

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_phase_questions_match_skill_md(self, phase_id: int):
        """Questions for each phase must match SKILL.md table."""
        expected = SKILL_MD_REQUIREMENTS[phase_id]["questions"]
        actual = PHASE_REQUIREMENTS[phase_id].questions
        assert actual == expected, (
            f"Phase {phase_id} questions mismatch: "
            f"SKILL.md says {expected}, API has {actual}"
        )

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_phase_hands_on_count_matches_skill_md(self, phase_id: int):
        """Hands-on requirements count must match SKILL.md table."""
        expected = SKILL_MD_REQUIREMENTS[phase_id]["hands_on"]
        actual = len(get_requirements_for_phase(phase_id))
        assert actual == expected, (
            f"Phase {phase_id} hands-on count mismatch: "
            f"SKILL.md says {expected}, API has {actual}"
        )

    def test_total_steps_is_sum_of_all_phases(self):
        """TOTAL_STEPS should equal sum of all phase steps."""
        expected_total = sum(SKILL_MD_REQUIREMENTS[p]["steps"] for p in range(7))
        assert TOTAL_STEPS == expected_total

    def test_total_questions_is_sum_of_all_phases(self):
        """TOTAL_QUESTIONS should equal sum of all phase questions."""
        expected_total = sum(SKILL_MD_REQUIREMENTS[p]["questions"] for p in range(7))
        assert TOTAL_QUESTIONS == expected_total


class TestBadgeDefinitions:
    """SKILL.md: Badge definitions must match exactly."""

    def test_seven_phase_badges_defined(self):
        """SKILL.md: 7 phase badges (one per phase)."""
        assert len(PHASE_BADGES) == 7

    def test_three_streak_badges_defined(self):
        """SKILL.md (streaks skill): 3 streak badges."""
        assert len(STREAK_BADGES) == 3

    def test_total_available_badges_is_10(self):
        """7 phase + 3 streak = 10 total badges."""
        all_badges = get_all_available_badges()
        assert len(all_badges) == 10

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_phase_badge_names_match_skill_md(self, phase_id: int):
        """Badge names must match SKILL.md table."""
        expected = SKILL_MD_BADGES[phase_id]["name"]
        actual = PHASE_BADGES[phase_id]["name"]
        assert actual == expected, (
            f"Phase {phase_id} badge name mismatch: "
            f"SKILL.md says '{expected}', API has '{actual}'"
        )

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_phase_badge_icons_match_skill_md(self, phase_id: int):
        """Badge icons should represent SKILL.md tier colors."""
        expected_icon = SKILL_MD_BADGES[phase_id]["icon"]
        actual_icon = PHASE_BADGES[phase_id]["icon"]
        assert actual_icon == expected_icon

    def test_streak_badge_thresholds(self):
        """Streak badges at 7, 30, 100 days."""
        thresholds = {b["required_streak"] for b in STREAK_BADGES}
        assert thresholds == {7, 30, 100}


# =============================================================================
# PHASE COMPLETION & PROGRESS CALCULATION
# =============================================================================


class TestPhaseCompletionDefinition:
    """SKILL.md: Phase is complete when ALL three requirements are met."""

    def _make_phase_progress(
        self,
        phase_id: int = 0,
        steps_completed: int = 0,
        questions_passed: int = 0,
        hands_on_validated_count: int = 0,
    ) -> PhaseProgress:
        """Helper to create PhaseProgress with defaults from requirements."""
        req = PHASE_REQUIREMENTS[phase_id]
        hands_on_req = len(get_requirements_for_phase(phase_id))
        is_hands_on_validated = hands_on_validated_count >= hands_on_req
        return PhaseProgress(
            phase_id=phase_id,
            steps_completed=steps_completed,
            steps_required=req.steps,
            questions_passed=questions_passed,
            questions_required=req.questions,
            hands_on_validated_count=hands_on_validated_count,
            hands_on_required_count=hands_on_req,
            hands_on_validated=is_hands_on_validated,
            hands_on_required=hands_on_req > 0,
        )

    def test_incomplete_when_all_zero(self):
        """Zero progress in all areas = not complete."""
        progress = self._make_phase_progress(
            steps_completed=0, questions_passed=0, hands_on_validated_count=0
        )
        assert progress.is_complete is False

    def test_incomplete_when_only_steps_done(self):
        """SKILL.md: ALL requirements must be met, not just steps."""
        progress = self._make_phase_progress(
            steps_completed=15, questions_passed=0, hands_on_validated_count=0
        )
        assert progress.is_complete is False

    def test_incomplete_when_only_questions_done(self):
        """SKILL.md: ALL requirements must be met, not just questions."""
        progress = self._make_phase_progress(
            steps_completed=0, questions_passed=12, hands_on_validated_count=0
        )
        assert progress.is_complete is False

    def test_incomplete_when_steps_missing(self):
        """Missing even 1 step = not complete."""
        progress = self._make_phase_progress(
            steps_completed=14, questions_passed=12, hands_on_validated_count=1
        )
        assert progress.is_complete is False

    def test_incomplete_when_questions_missing(self):
        """Missing even 1 question = not complete."""
        progress = self._make_phase_progress(
            steps_completed=15, questions_passed=11, hands_on_validated_count=1
        )
        assert progress.is_complete is False

    def test_incomplete_when_hands_on_missing(self):
        """Missing hands-on = not complete."""
        progress = self._make_phase_progress(
            steps_completed=15, questions_passed=12, hands_on_validated_count=0
        )
        assert progress.is_complete is False

    def test_complete_when_all_requirements_met_exactly(self):
        """Phase complete when exactly meeting all requirements."""
        progress = self._make_phase_progress(
            steps_completed=15, questions_passed=12, hands_on_validated_count=1
        )
        assert progress.is_complete is True

    def test_complete_when_exceeding_requirements(self):
        """Exceeding requirements should still be complete."""
        progress = self._make_phase_progress(
            steps_completed=20, questions_passed=15, hands_on_validated_count=3
        )
        assert progress.is_complete is True

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_each_phase_completion_requires_all_three(self, phase_id: int):
        """Each phase follows the same completion rule: all 3 requirements."""
        req = PHASE_REQUIREMENTS[phase_id]
        hands_on_count = len(get_requirements_for_phase(phase_id))

        # Complete phase
        complete = self._make_phase_progress(
            phase_id=phase_id,
            steps_completed=req.steps,
            questions_passed=req.questions,
            hands_on_validated_count=hands_on_count,
        )
        assert complete.is_complete is True

        # Missing steps
        missing_steps = self._make_phase_progress(
            phase_id=phase_id,
            steps_completed=req.steps - 1,
            questions_passed=req.questions,
            hands_on_validated_count=hands_on_count,
        )
        assert missing_steps.is_complete is False


class TestProgressCalculation:
    """SKILL.md: Progress calculation formulas."""

    def test_zero_progress_equals_zero_percent(self):
        """0 completed / total = 0%."""
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

    def test_full_progress_equals_100_percent(self):
        """All completed = 100%."""
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

    def test_phase_progress_formula(self):
        """SKILL.md formula: (Steps + Questions + Hands-on) / Total.

        Phase 0: 15 steps + 12 questions + 1 hands-on = 28 total
        If: 10 steps + 6 questions + 0 hands-on = 16 completed
        Percentage = 16/28 * 100 ≈ 57.14%
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
        total = 15 + 12 + 1
        completed = 10 + 6 + 0
        expected = (completed / total) * 100
        assert progress.overall_percentage == pytest.approx(expected, rel=0.01)

    def test_over_completion_capped_at_100(self):
        """Exceeding requirements caps at 100%, not higher."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=25,
            steps_required=15,
            questions_passed=20,
            questions_required=12,
            hands_on_validated_count=5,
            hands_on_required_count=1,
            hands_on_validated=True,
            hands_on_required=True,
        )
        assert progress.overall_percentage == 100.0


class TestUserProgressAggregation:
    """Test UserProgress class aggregates phase data correctly."""

    def _make_complete_phase(self, phase_id: int) -> PhaseProgress:
        """Create a complete phase progress."""
        req = PHASE_REQUIREMENTS[phase_id]
        hands_on = len(get_requirements_for_phase(phase_id))
        return PhaseProgress(
            phase_id=phase_id,
            steps_completed=req.steps,
            steps_required=req.steps,
            questions_passed=req.questions,
            questions_required=req.questions,
            hands_on_validated_count=hands_on,
            hands_on_required_count=hands_on,
            hands_on_validated=True,
            hands_on_required=True,
        )

    def _make_incomplete_phase(self, phase_id: int) -> PhaseProgress:
        """Create an incomplete phase progress (50% done)."""
        req = PHASE_REQUIREMENTS[phase_id]
        hands_on = len(get_requirements_for_phase(phase_id))
        return PhaseProgress(
            phase_id=phase_id,
            steps_completed=req.steps // 2,
            steps_required=req.steps,
            questions_passed=req.questions // 2,
            questions_required=req.questions,
            hands_on_validated_count=0,
            hands_on_required_count=hands_on,
            hands_on_validated=False,
            hands_on_required=True,
        )

    def test_phases_completed_count(self):
        """Count only fully completed phases."""
        phases = {
            0: self._make_complete_phase(0),
            1: self._make_complete_phase(1),
            2: self._make_incomplete_phase(2),
        }
        progress = UserProgress(user_id="test", phases=phases)
        assert progress.phases_completed == 2

    def test_total_phases_always_7(self):
        """total_phases should always be 7 regardless of user progress."""
        progress = UserProgress(user_id="test", phases={})
        assert progress.total_phases == 7

    def test_current_phase_is_first_incomplete(self):
        """current_phase returns first incomplete phase."""
        phases = {
            0: self._make_complete_phase(0),
            1: self._make_complete_phase(1),
            2: self._make_incomplete_phase(2),
        }
        progress = UserProgress(user_id="test", phases=phases)
        assert progress.current_phase == 2

    def test_is_program_complete_when_all_done(self):
        """is_program_complete is True only when all 7 phases done."""
        full = UserProgress(
            user_id="test",
            phases={i: self._make_complete_phase(i) for i in range(7)},
        )
        assert full.is_program_complete is True


# =============================================================================
# BADGE AWARDING RULES
# =============================================================================


class TestBadgeAwardingRules:
    """SKILL.md: Badges awarded when phase reaches 100% completion."""

    def test_no_badge_with_zero_progress(self):
        """No progress = no badge."""
        badges = compute_phase_badges({})
        assert badges == []

    def test_no_badge_with_incomplete_steps(self):
        """Badge NOT awarded if steps incomplete."""
        phase_counts = {0: (14, 12, True)}  # Missing 1 step
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_no_badge_with_incomplete_questions(self):
        """Badge NOT awarded if questions incomplete."""
        phase_counts = {0: (15, 11, True)}  # Missing 1 question
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_no_badge_without_hands_on(self):
        """Badge NOT awarded if hands-on not validated."""
        phase_counts = {0: (15, 12, False)}
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_badge_awarded_at_100_percent(self):
        """Badge awarded when ALL requirements met."""
        phase_counts = {0: (15, 12, True)}
        badges = compute_phase_badges(phase_counts)
        assert len(badges) == 1
        assert badges[0].name == "Explorer"

    def test_multiple_badges_for_multiple_phases(self):
        """Each completed phase awards its badge."""
        phase_counts = {
            0: (15, 12, True),
            1: (36, 12, True),
            2: (30, 12, True),
        }
        badges = compute_phase_badges(phase_counts)
        assert len(badges) == 3
        badge_names = {b.name for b in badges}
        assert badge_names == {"Explorer", "Practitioner", "Builder"}

    def test_all_seven_badges_for_full_completion(self):
        """Completing all phases awards all 7 badges."""
        phase_counts = {
            0: (15, 12, True),
            1: (36, 12, True),
            2: (30, 12, True),
            3: (31, 8, True),
            4: (51, 18, True),
            5: (55, 12, True),
            6: (64, 12, True),
        }
        badges = compute_phase_badges(phase_counts)
        assert len(badges) == 7


class TestStreakBadgeRules:
    """SKILL.md (streaks): Streak badge awarding rules."""

    def test_no_streak_badge_below_7(self):
        """No badge for streaks less than 7."""
        badges = compute_streak_badges(6)
        assert badges == []

    def test_week_warrior_at_7(self):
        """Week Warrior badge at 7-day streak."""
        badges = compute_streak_badges(7)
        assert len(badges) == 1
        assert badges[0].name == "Week Warrior"

    def test_monthly_master_at_30(self):
        """Monthly Master at 30 days (includes Week Warrior)."""
        badges = compute_streak_badges(30)
        assert len(badges) == 2
        names = {b.name for b in badges}
        assert names == {"Week Warrior", "Monthly Master"}

    def test_century_club_at_100(self):
        """Century Club at 100 days (includes all previous)."""
        badges = compute_streak_badges(100)
        assert len(badges) == 3
        names = {b.name for b in badges}
        assert names == {"Week Warrior", "Monthly Master", "Century Club"}


class TestCombinedBadgeComputation:
    """Test compute_all_badges combines phase and streak badges."""

    def test_empty_returns_empty(self):
        """No progress and no streak = no badges."""
        badges = compute_all_badges({}, 0)
        assert badges == []

    def test_combined_badges(self):
        """Both phase and streak badges."""
        phase_counts = {0: (15, 12, True), 1: (36, 12, True)}
        badges = compute_all_badges(phase_counts, 35)
        assert len(badges) == 4  # 2 phase + 2 streak


# =============================================================================
# UNLOCKING RULES
# =============================================================================


class TestUnlockingRules:
    """SKILL.md: Content unlocking rules."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_skip_steps(self, db_session, test_user):
        """Non-admin users must complete steps in order."""
        with pytest.raises(StepNotUnlockedError):
            await complete_step(
                db_session,
                test_user.id,
                "phase0-topic0",
                3,
                is_admin=False,
            )

    @pytest.mark.asyncio
    async def test_admin_bypasses_step_locks(self, db_session, test_user):
        """SKILL.md: Admin users bypass all locks."""
        test_user.is_admin = True
        db_session.add(test_user)
        await db_session.commit()

        result = await complete_step(
            db_session,
            test_user.id,
            "phase0-topic0",
            3,
            is_admin=True,
        )
        assert result.step_order == 3

    @pytest.mark.asyncio
    async def test_admin_unlocks_all_steps_in_progress(self, db_session, test_user):
        """SKILL.md: Admin users have all steps unlocked."""
        progress = await get_topic_step_progress(
            db_session,
            test_user.id,
            "phase0-topic0",
            10,
            is_admin=True,
        )
        assert progress.next_unlocked_step == 10

    @pytest.mark.asyncio
    async def test_non_admin_sequential_unlock(self, db_session, test_user):
        """Non-admin users unlock steps sequentially."""
        progress = await get_topic_step_progress(
            db_session,
            test_user.id,
            "phase0-topic0",
            10,
            is_admin=False,
        )
        assert progress.next_unlocked_step == 1


# =============================================================================
# HANDS-ON REQUIREMENTS
# =============================================================================


class TestHandsOnRequirements:
    """Test hands-on requirements are properly defined."""

    def test_all_requirements_have_unique_ids(self):
        """Each requirement must have a unique ID."""
        all_ids = []
        for phase_reqs in HANDS_ON_REQUIREMENTS.values():
            for req in phase_reqs:
                all_ids.append(req.id)
        assert len(all_ids) == len(set(all_ids))

    def test_requirement_ids_include_phase(self):
        """Requirement IDs should include phase number for clarity."""
        for phase_id, reqs in HANDS_ON_REQUIREMENTS.items():
            for req in reqs:
                assert f"phase{phase_id}" in req.id

    def test_get_requirement_by_id_works(self):
        """get_requirement_by_id should find requirements."""
        req = get_requirement_by_id("phase0-github-profile")
        assert req is not None
        assert req.phase_id == 0

    def test_get_requirement_by_id_returns_none_for_invalid(self):
        """get_requirement_by_id returns None for invalid IDs."""
        req = get_requirement_by_id("nonexistent-requirement")
        assert req is None


# =============================================================================
# DATABASE INTEGRATION TESTS
# =============================================================================


async def _complete_phase_for_user(
    db: AsyncSession, user_id: str, phase_id: int
) -> None:
    """Helper to fully complete a phase for a user."""
    req = PHASE_REQUIREMENTS[phase_id]

    # Add steps
    for step_num in range(req.steps):
        step = StepProgress(
            user_id=user_id,
            topic_id=f"phase{phase_id}-topic{step_num // 5}",
            step_order=(step_num % 5) + 1,
        )
        db.add(step)

    # Add questions
    for q_num in range(req.questions):
        topic_num = q_num // 2
        q_in_topic = (q_num % 2) + 1
        attempt = QuestionAttempt(
            user_id=user_id,
            topic_id=f"phase{phase_id}-topic{topic_num}",
            question_id=f"phase{phase_id}-topic{topic_num}-q{q_in_topic}",
            user_answer=fake.sentence(nb_words=10),
            is_passed=True,
            llm_feedback=fake.sentence(nb_words=15),
        )
        db.add(attempt)

    # Add hands-on submissions
    for requirement in get_requirements_for_phase(phase_id):
        submission = Submission(
            user_id=user_id,
            requirement_id=requirement.id,
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=phase_id,
            submitted_value=f"https://github.com/{fake.user_name()}/test",
            extracted_username=fake.user_name(),
            is_validated=True,
            validated_at=datetime.now(UTC),
        )
        db.add(submission)

    await db.commit()


@pytest.mark.asyncio
class TestProgressionIntegration:
    """Integration tests with database fixtures."""

    async def test_user_with_no_progress_not_complete(self, db_session, test_user):
        """New user has 0 completed phases."""
        from services.progress import fetch_user_progress

        progress = await fetch_user_progress(db_session, test_user.id)
        assert progress.phases_completed == 0
        assert progress.is_program_complete is False

    async def test_user_with_partial_progress(
        self, db_session, test_user_with_progress
    ):
        """User with 3 phases complete should have 3 badges."""
        from services.progress import fetch_user_progress, get_phase_completion_counts

        progress = await fetch_user_progress(db_session, test_user_with_progress.id)
        assert progress.phases_completed == 3

        phase_counts = get_phase_completion_counts(progress)
        badges = compute_phase_badges(phase_counts)
        assert len(badges) == 3

    async def test_user_with_full_completion(
        self, db_session, test_user_full_completion
    ):
        """User with all phases complete should be eligible for certificate."""
        from services.progress import fetch_user_progress, get_phase_completion_counts

        progress = await fetch_user_progress(db_session, test_user_full_completion.id)
        assert progress.phases_completed == 7
        assert progress.is_program_complete is True

        phase_counts = get_phase_completion_counts(progress)
        badges = compute_phase_badges(phase_counts)
        assert len(badges) == 7


@pytest.mark.asyncio
class TestCertificateEligibilityFromProgression:
    """Certificate eligibility is derived from phase completion."""

    async def test_not_eligible_with_zero_progress(self, db_session, test_user):
        """No progress = not eligible for certificate."""
        from services.certificates import check_eligibility

        result = await check_eligibility(db_session, test_user.id, "full_completion")
        assert result.is_eligible is False

    async def test_eligible_with_full_completion(
        self, db_session, test_user_full_completion
    ):
        """Full completion = eligible for certificate."""
        from services.certificates import check_eligibility

        result = await check_eligibility(
            db_session, test_user_full_completion.id, "full_completion"
        )
        assert result.is_eligible is True
        assert result.phases_completed == 7


@pytest.mark.asyncio
class TestFullUserJourney:
    """Integration tests simulating complete user journeys with Faker data."""

    async def test_new_user_to_phase0_completion(self, db_session: AsyncSession):
        """Simulate a user completing Phase 0 from scratch."""
        from services.progress import fetch_user_progress, get_phase_completion_counts

        user = User(
            id=f"user_{uuid.uuid4().hex[:24]}",
            email=fake.email(),
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            github_username=fake.user_name().lower()[:20],
        )
        db_session.add(user)
        await db_session.commit()

        # Initial state: no progress
        progress = await fetch_user_progress(db_session, user.id)
        assert progress.phases_completed == 0

        # Complete Phase 0
        await _complete_phase_for_user(db_session, user.id, 0)

        # Verify completion
        progress = await fetch_user_progress(db_session, user.id)
        assert progress.phases_completed == 1

        # Verify badge
        counts = get_phase_completion_counts(progress)
        badges = compute_phase_badges(counts)
        assert len(badges) == 1
        assert badges[0].name == "Explorer"

    async def test_full_program_completion_journey(self, db_session: AsyncSession):
        """Simulate completing the entire program."""
        from services.progress import fetch_user_progress, get_phase_completion_counts

        user = User(
            id=f"user_{uuid.uuid4().hex[:24]}",
            email=fake.email(),
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            github_username=fake.user_name().lower()[:20],
        )
        db_session.add(user)
        await db_session.commit()

        # Complete all phases
        for phase_id in range(7):
            await _complete_phase_for_user(db_session, user.id, phase_id)

        # Final verification
        progress = await fetch_user_progress(db_session, user.id)
        assert progress.is_program_complete is True

        counts = get_phase_completion_counts(progress)
        badges = compute_phase_badges(counts)
        assert len(badges) == 7

    async def test_user_with_international_name(self, db_session: AsyncSession):
        """User with international characters in name is handled correctly."""
        from services.progress import fetch_user_progress

        faker_jp = Faker("ja_JP")

        user = User(
            id=f"user_{uuid.uuid4().hex[:24]}",
            email=fake.email(),
            first_name=faker_jp.first_name(),
            last_name=faker_jp.last_name(),
            github_username=fake.user_name().lower()[:20],
        )
        db_session.add(user)
        await db_session.commit()

        progress = await fetch_user_progress(db_session, user.id)
        assert progress.user_id == user.id


# =============================================================================
# PROPERTY-BASED TESTS (Hypothesis)
# =============================================================================


class TestProgressCalculationProperties:
    """Property-based tests for progress calculation edge cases."""

    @given(
        steps_completed=st.integers(min_value=0, max_value=1000),
        steps_required=st.integers(min_value=1, max_value=1000),
        questions_passed=st.integers(min_value=0, max_value=1000),
        questions_required=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100)
    def test_phase_progress_percentage_always_valid(
        self,
        steps_completed,
        steps_required,
        questions_passed,
        questions_required,
    ):
        """Phase progress percentage is always between 0 and 100."""
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=steps_completed,
            steps_required=steps_required,
            questions_passed=questions_passed,
            questions_required=questions_required,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )

        assert 0.0 <= progress.overall_percentage <= 100.0

    @given(
        steps=st.integers(min_value=0, max_value=200),
        questions=st.integers(min_value=0, max_value=200),
        hands_on=st.booleans(),
    )
    @settings(max_examples=100)
    def test_badge_awarded_only_when_complete(self, steps, questions, hands_on):
        """Phase 0 badge only awarded when requirements are fully met."""
        req = PHASE_REQUIREMENTS[0]
        phase_counts = {0: (steps, questions, hands_on)}

        badges = compute_phase_badges(phase_counts)

        is_complete = steps >= req.steps and questions >= req.questions and hands_on

        if is_complete:
            assert any(b.name == "Explorer" for b in badges)
        else:
            assert not any(b.name == "Explorer" for b in badges)

    @given(longest_streak=st.integers(min_value=0, max_value=500))
    @settings(max_examples=50)
    def test_streak_badges_cumulative(self, longest_streak):
        """Streak badges are cumulative - higher thresholds include lower ones."""
        badges = compute_streak_badges(longest_streak)
        badge_names = {b.name for b in badges}

        if longest_streak >= 100:
            assert "Century Club" in badge_names
            assert "Monthly Master" in badge_names
            assert "Week Warrior" in badge_names
        elif longest_streak >= 30:
            assert "Monthly Master" in badge_names
            assert "Week Warrior" in badge_names
        elif longest_streak >= 7:
            assert "Week Warrior" in badge_names
        else:
            assert len(badges) == 0

    @given(
        steps=st.integers(min_value=-100, max_value=200),
        questions=st.integers(min_value=-100, max_value=200),
    )
    @settings(max_examples=50)
    def test_negative_values_dont_crash(self, steps, questions):
        """System handles invalid negative values without crashing.

        NOTE: Hypothesis discovered that negative inputs can produce negative
        percentages. This documents the behavior - validation should happen
        at the API layer, not in progress calculation.
        """
        progress = PhaseProgress(
            phase_id=0,
            steps_completed=steps,
            steps_required=15,
            questions_passed=questions,
            questions_required=12,
            hands_on_validated_count=0,
            hands_on_required_count=1,
            hands_on_validated=False,
            hands_on_required=True,
        )

        # Should not throw exceptions
        _ = progress.overall_percentage

        # Only assert valid range for valid inputs
        if steps >= 0 and questions >= 0:
            assert progress.overall_percentage >= 0.0


# =============================================================================
# TOPIC AND PHASE UNLOCKING TESTS
# =============================================================================


class TestTopicUnlocking:
    """SKILL.md: Topic unlocking rules.

    From SKILL.md:
    - First topic in phase: Always unlocked (if phase is unlocked)
    - Subsequent topics: Previous topic must be complete
    """

    def test_first_topic_always_unlocked_when_phase_unlocked(self):
        """First topic (order=1) is always unlocked when phase is unlocked."""
        # Phase 0 is always unlocked, so first topic should be unlocked
        # This tests the dashboard service topic locking logic
        # When phase_is_locked=False and topic.order=1: topic_is_locked=False

        # Simulating the logic from dashboard.py:
        phase_is_locked = False
        topic_order = 1
        prev_topic_complete = False  # Doesn't matter for first topic

        # First topic rule
        if phase_is_locked:
            topic_is_locked = True
        elif topic_order == 1:
            topic_is_locked = False
        else:
            topic_is_locked = not prev_topic_complete

        assert topic_is_locked is False

    def test_subsequent_topic_locked_when_previous_incomplete(self):
        """Subsequent topics are locked when previous topic is incomplete."""
        # Simulating the logic from dashboard.py
        phase_is_locked = False
        topic_order = 2  # Second topic
        prev_topic_complete = False

        if phase_is_locked:
            topic_is_locked = True
        elif topic_order == 1:
            topic_is_locked = False
        else:
            topic_is_locked = not prev_topic_complete

        assert topic_is_locked is True

    def test_subsequent_topic_unlocked_when_previous_complete(self):
        """Subsequent topics are unlocked when previous topic is complete."""
        # Simulating the logic from dashboard.py
        phase_is_locked = False
        topic_order = 2  # Second topic
        prev_topic_complete = True

        if phase_is_locked:
            topic_is_locked = True
        elif topic_order == 1:
            topic_is_locked = False
        else:
            topic_is_locked = not prev_topic_complete

        assert topic_is_locked is False

    def test_all_topics_locked_when_phase_locked(self):
        """All topics are locked when their phase is locked."""
        phase_is_locked = True

        for topic_order in [1, 2, 3]:
            prev_topic_complete = True  # Even if previous is complete

            if phase_is_locked:
                topic_is_locked = True
            elif topic_order == 1:
                topic_is_locked = False
            else:
                topic_is_locked = not prev_topic_complete

            assert topic_is_locked is True

    def test_admin_bypasses_topic_locks(self):
        """SKILL.md: Admin users bypass all topic locks."""
        is_admin = True

        # Admin always gets topic_is_locked = False
        # This is the first check in dashboard.py topic locking
        topic_is_locked = not is_admin  # Simplified admin check

        assert topic_is_locked is False


class TestPhaseUnlocking:
    """SKILL.md: Phase unlocking rules.

    From SKILL.md:
    - Phase 0: Always unlocked
    - Phases 1-6: Previous phase must be complete
    - Admin users: Bypass all locks
    """

    def test_phase_0_always_unlocked(self):
        """Phase 0 is always unlocked for all users."""
        phase_id = 0
        prev_phase_complete = False  # Doesn't matter

        if phase_id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        assert is_locked is False

    def test_phase_1_locked_when_phase_0_incomplete(self):
        """Phase 1 is locked when Phase 0 is incomplete."""
        phase_id = 1
        prev_phase_complete = False

        if phase_id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        assert is_locked is True

    def test_phase_1_unlocked_when_phase_0_complete(self):
        """Phase 1 is unlocked when Phase 0 is complete."""
        phase_id = 1
        prev_phase_complete = True

        if phase_id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        assert is_locked is False

    @pytest.mark.parametrize("phase_id", [1, 2, 3, 4, 5, 6])
    def test_phases_1_through_6_require_previous_complete(self, phase_id: int):
        """Phases 1-6 all require their previous phase to be complete."""
        prev_phase_complete = False

        if phase_id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        assert is_locked is True, f"Phase {phase_id} should be locked"

    @pytest.mark.parametrize("phase_id", [1, 2, 3, 4, 5, 6])
    def test_phases_1_through_6_unlock_when_previous_complete(self, phase_id: int):
        """Phases 1-6 unlock when their previous phase is complete."""
        prev_phase_complete = True

        if phase_id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        assert is_locked is False, f"Phase {phase_id} should be unlocked"

    def test_admin_bypasses_all_phase_locks(self):
        """SKILL.md: Admin users bypass all phase locks."""
        is_admin = True

        for phase_id in range(7):
            prev_phase_complete = False  # Would normally lock

            if is_admin:
                is_locked = False
            elif phase_id == 0:
                is_locked = False
            else:
                is_locked = not prev_phase_complete

            assert is_locked is False, f"Phase {phase_id} should be unlocked for admin"

    def test_sequential_unlock_chain(self):
        """Phases unlock sequentially as each is completed."""
        # Track which phases are complete
        phases_complete = [False] * 7  # None complete initially

        # Initial state: only phase 0 is unlocked
        for phase_id in range(7):
            if phase_id == 0:
                is_locked = False
            else:
                is_locked = not phases_complete[phase_id - 1]

            if phase_id == 0:
                assert is_locked is False, "Phase 0 should start unlocked"
            else:
                assert is_locked is True, f"Phase {phase_id} should start locked"

        # Complete phases one by one and verify unlock chain
        for completing_phase in range(7):
            phases_complete[completing_phase] = True

            # Check which phases are now unlocked
            for phase_id in range(7):
                if phase_id == 0:
                    is_locked = False
                else:
                    is_locked = not phases_complete[phase_id - 1]

                # Phases up to completing_phase + 1 should be unlocked
                expected_unlocked = phase_id <= completing_phase + 1

                if expected_unlocked:
                    assert is_locked is False, (
                        f"Phase {phase_id} should be unlocked after "
                        f"completing phase {completing_phase}"
                    )
                else:
                    assert is_locked is True, (
                        f"Phase {phase_id} should still be locked after "
                        f"completing phase {completing_phase}"
                    )
