"""Dashboard service.

This module provides dashboard data by combining:
- Static content from JSON files
- User progress from the database
- Locking logic based on the progression system

Source of truth: .github/skills/progression-system/progression-system.md
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.config import get_settings
from models import Submission
from repositories.progress_repository import (
    QuestionAttemptRepository,
    StepProgressRepository,
)
from repositories.submission_repository import SubmissionRepository
from schemas import (
    BadgeData,
    DashboardData,
    HandsOnSubmissionResponse,
    Phase,
    PhaseDetailData,
    PhaseProgressData,
    PhaseSummaryData,
    QuestionLockout,
    Topic,
    TopicDetailData,
    TopicProgressData,
    TopicSummaryData,
    UserSummaryData,
)
from services.activity_service import get_streak_data
from services.badges_service import compute_all_badges
from services.content_service import (
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_slugs,
)
from services.phase_requirements_service import get_requirements_for_phase
from services.progress_service import (
    compute_topic_progress,
    fetch_user_progress,
    get_phase_completion_counts,
    is_phase_locked,
    is_topic_complete,
    is_topic_locked,
    phase_progress_to_data,
)

logger = get_logger(__name__)


def _build_phase_summary(
    phase: Phase,
    progress_data: PhaseProgressData | None,
    locked: bool,
) -> PhaseSummaryData:
    """Build PhaseSummaryData from a Phase and computed values.

    Centralizes PhaseSummaryData construction to avoid repetition.
    """
    return PhaseSummaryData(
        id=phase.id,
        name=phase.name,
        slug=phase.slug,
        description=phase.description,
        short_description=phase.short_description,
        estimated_weeks=phase.estimated_weeks,
        order=phase.order,
        topics_count=len(phase.topics),
        objectives=list(phase.objectives),
        capstone=phase.capstone,
        hands_on_verification=phase.hands_on_verification,
        progress=progress_data,
        is_locked=locked,
    )


def _build_topic_summary(
    topic: Topic,
    progress: TopicProgressData | None,
    locked: bool,
) -> TopicSummaryData:
    """Build TopicSummaryData from a Topic and computed values.

    Centralizes TopicSummaryData construction to avoid repetition.
    """
    return TopicSummaryData(
        id=topic.id,
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        order=topic.order,
        estimated_time=topic.estimated_time,
        is_capstone=topic.is_capstone,
        steps_count=len(topic.learning_steps),
        questions_count=len(topic.questions),
        progress=progress,
        is_locked=locked,
    )


def _to_hands_on_submission_data(submission: Submission) -> HandsOnSubmissionResponse:
    # Avoid importing ORM models into routes layer; service returns response model.
    return HandsOnSubmissionResponse(
        id=submission.id,
        requirement_id=submission.requirement_id,
        submission_type=submission.submission_type,
        phase_id=submission.phase_id,
        submitted_value=submission.submitted_value,
        extracted_username=submission.extracted_username,
        is_validated=submission.is_validated,
        validated_at=submission.validated_at,
        created_at=submission.created_at,
        feedback_json=submission.feedback_json,
    )


async def get_dashboard(
    db: AsyncSession,
    user_id: str,
    user_email: str,
    user_first_name: str | None,
    user_last_name: str | None,
    user_avatar_url: str | None,
    user_github_username: str | None,
    is_admin: bool,
) -> DashboardData:
    """Get complete dashboard data for a user.

    Locking rules:
    - Phase 0: Always unlocked
    - Phases 1-6: Previous phase must be complete
    - Admin users: Bypass all locks
    """
    phases = get_all_phases()
    user_progress = await fetch_user_progress(db, user_id)

    phase_summaries: list[PhaseSummaryData] = []
    for phase in phases:
        progress = user_progress.phases.get(phase.id)
        progress_data = phase_progress_to_data(progress) if progress else None
        locked = is_phase_locked(phase.id, user_progress, is_admin)
        phase_summaries.append(_build_phase_summary(phase, progress_data, locked))

    overall_percentage = user_progress.overall_percentage
    phases_completed = user_progress.phases_completed
    current_phase = user_progress.current_phase

    phase_completion_counts = get_phase_completion_counts(user_progress)
    streak_data = await get_streak_data(db, user_id)

    earned_badges = compute_all_badges(
        phase_completion_counts=phase_completion_counts,
        longest_streak=streak_data.longest_streak,
        user_id=user_id,
    )
    badges = [
        BadgeData(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
        )
        for badge in earned_badges
    ]

    return DashboardData(
        user=UserSummaryData(
            id=user_id,
            email=user_email,
            first_name=user_first_name,
            last_name=user_last_name,
            avatar_url=user_avatar_url,
            github_username=user_github_username,
            is_admin=is_admin,
        ),
        phases=phase_summaries,
        overall_progress=round(overall_percentage, 1),
        phases_completed=phases_completed,
        phases_total=len(phases),
        current_phase=current_phase,
        badges=badges,
    )


async def get_phases_list(
    db: AsyncSession,
    user_id: str | None,
    is_admin: bool,
) -> list[PhaseSummaryData]:
    """Get all phases with progress for a user.

    If user_id is None (unauthenticated):
    - No progress data
    - Only Phase 0 is unlocked
    """
    phases = get_all_phases()

    if user_id is None:
        return [
            _build_phase_summary(phase, None, is_phase_locked(phase.id, None, False))
            for phase in phases
        ]

    user_progress = await fetch_user_progress(db, user_id)

    return [
        _build_phase_summary(
            phase,
            phase_progress_to_data(progress)
            if (progress := user_progress.phases.get(phase.id))
            else None,
            is_phase_locked(phase.id, user_progress, is_admin),
        )
        for phase in phases
    ]


async def get_phase_detail(
    db: AsyncSession,
    user_id: str | None,
    phase_slug: str,
    is_admin: bool,
) -> PhaseDetailData | None:
    """Get detailed phase info with topics and progress.

    Topic locking rules:
    - First topic in phase: Always unlocked (if phase is unlocked)
    - Subsequent topics: Previous topic must be complete
    - Admin users: Bypass all locks
    """
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None

    if user_id is None:
        phase_is_locked = is_phase_locked(phase.id, None, False)

        topic_summaries: list[TopicSummaryData] = []
        for topic in phase.topics:
            # For unauthenticated: first topic unlocked if phase unlocked, rest locked
            locked = is_topic_locked(topic.order, phase_is_locked, False, False)
            topic_summaries.append(_build_topic_summary(topic, None, locked))

        hands_on_reqs = get_requirements_for_phase(phase.id)

        return PhaseDetailData(
            id=phase.id,
            name=phase.name,
            slug=phase.slug,
            description=phase.description,
            short_description=phase.short_description,
            estimated_weeks=phase.estimated_weeks,
            order=phase.order,
            objectives=list(phase.objectives),
            capstone=phase.capstone,
            hands_on_verification=phase.hands_on_verification,
            topics=topic_summaries,
            progress=None,
            hands_on_requirements=list(hands_on_reqs),
            hands_on_submissions=[],
            is_locked=phase_is_locked,
            all_topics_complete=False,
            all_hands_on_validated=False,
            is_phase_complete=False,
        )

    user_progress = await fetch_user_progress(db, user_id)
    phase_progress = user_progress.phases.get(phase.id)
    phase_is_locked = is_phase_locked(phase.id, user_progress, is_admin)

    # Batch queries to avoid N+1 (2 queries instead of 2*N)
    step_repo = StepProgressRepository(db)
    question_repo = QuestionAttemptRepository(db)

    all_steps_by_topic = await step_repo.get_all_completed_by_user(user_id)
    all_questions_by_topic = await question_repo.get_all_passed_by_user(user_id)

    phase_topic_ids = {topic.id for topic in phase.topics}
    steps_by_topic: dict[str, set[int]] = {
        tid: steps
        for tid, steps in all_steps_by_topic.items()
        if tid in phase_topic_ids
    }
    questions_by_topic: dict[str, set[str]] = {
        tid: qs for tid, qs in all_questions_by_topic.items() if tid in phase_topic_ids
    }

    topic_summaries: list[TopicSummaryData] = []
    prev_topic_complete = True

    for topic in phase.topics:
        completed_steps = steps_by_topic.get(topic.id, set())
        passed_questions = questions_by_topic.get(topic.id, set())

        topic_progress = compute_topic_progress(
            topic, completed_steps, passed_questions
        )

        locked = is_topic_locked(
            topic.order, phase_is_locked, prev_topic_complete, is_admin
        )
        topic_summaries.append(_build_topic_summary(topic, topic_progress, locked))

        prev_topic_complete = is_topic_complete(
            topic, completed_steps, passed_questions
        )

    # Get hands-on requirements and submissions
    hands_on_reqs = get_requirements_for_phase(phase.id)
    submission_repo = SubmissionRepository(db)
    db_submissions = await submission_repo.get_by_user_and_phase(user_id, phase.id)
    hands_on_submissions = [_to_hands_on_submission_data(sub) for sub in db_submissions]

    progress_data = phase_progress_to_data(phase_progress) if phase_progress else None

    # Business logic lives here, NOT in frontend
    all_topics_complete = is_admin or all(
        t.progress and t.progress.status == "completed" for t in topic_summaries
    )

    validated_req_ids = {
        sub.requirement_id for sub in db_submissions if sub.is_validated
    }
    required_ids = {req.id for req in hands_on_reqs}
    all_hands_on_validated = required_ids.issubset(validated_req_ids)

    # Use authoritative phase completion from services/progress.py.
    # Single source of truth for certificates, badges, and other features.
    is_phase_complete = phase_progress.is_complete if phase_progress else False

    return PhaseDetailData(
        id=phase.id,
        name=phase.name,
        slug=phase.slug,
        description=phase.description,
        short_description=phase.short_description,
        estimated_weeks=phase.estimated_weeks,
        order=phase.order,
        objectives=list(phase.objectives),
        capstone=phase.capstone,
        hands_on_verification=phase.hands_on_verification,
        topics=topic_summaries,
        progress=progress_data,
        hands_on_requirements=list(hands_on_reqs),
        hands_on_submissions=hands_on_submissions,
        is_locked=phase_is_locked,
        all_topics_complete=all_topics_complete,
        all_hands_on_validated=all_hands_on_validated,
        is_phase_complete=is_phase_complete,
    )


async def get_topic_detail(
    db: AsyncSession,
    user_id: str | None,
    phase_slug: str,
    topic_slug: str,
    is_admin: bool,
) -> TopicDetailData | None:
    """Get detailed topic info with steps, questions, and progress."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None

    topic = get_topic_by_slugs(phase_slug, topic_slug)
    if not topic:
        return None

    learning_steps = list(topic.learning_steps)
    questions = list(topic.questions)
    learning_objectives = list(topic.learning_objectives)

    if user_id is None:
        phase_is_locked = is_phase_locked(phase.id, None, False)
        # For unauthenticated: first topic unlocked if phase unlocked, rest locked
        topic_locked = is_topic_locked(topic.order, phase_is_locked, False, False)

        # Get previous topic name for UI
        topic_index = next(
            (i for i, t in enumerate(phase.topics) if t.id == topic.id), 0
        )
        previous_topic_name = (
            phase.topics[topic_index - 1].name if topic_index > 0 else None
        )

        return TopicDetailData(
            id=topic.id,
            slug=topic.slug,
            name=topic.name,
            description=topic.description,
            order=topic.order,
            estimated_time=topic.estimated_time,
            is_capstone=topic.is_capstone,
            learning_steps=learning_steps,
            questions=questions,
            learning_objectives=learning_objectives,
            progress=None,
            completed_step_orders=[],
            passed_question_ids=[],
            is_locked=phase_is_locked,
            is_topic_locked=topic_locked,
            previous_topic_name=previous_topic_name,
        )

    user_progress = await fetch_user_progress(db, user_id)
    phase_is_locked = is_phase_locked(phase.id, user_progress, is_admin)

    # Batch queries to avoid N+1
    step_repo = StepProgressRepository(db)
    question_repo = QuestionAttemptRepository(db)

    all_steps_by_topic = await step_repo.get_all_completed_by_user(user_id)
    all_questions_by_topic = await question_repo.get_all_passed_by_user(user_id)

    completed_steps = all_steps_by_topic.get(topic.id, set())
    passed_question_ids = all_questions_by_topic.get(topic.id, set())

    topic_progress = compute_topic_progress(topic, completed_steps, passed_question_ids)

    # Determine topic locking and get previous topic info for UI
    topic_index = next((i for i, t in enumerate(phase.topics) if t.id == topic.id), 0)
    previous_topic_name: str | None = None
    prev_topic_complete = True  # First topic has no previous, so consider it "complete"

    if topic_index > 0:
        prev_topic = phase.topics[topic_index - 1]
        previous_topic_name = prev_topic.name
        prev_completed_steps = all_steps_by_topic.get(prev_topic.id, set())
        prev_passed_questions = all_questions_by_topic.get(prev_topic.id, set())
        prev_topic_complete = is_topic_complete(
            prev_topic, prev_completed_steps, prev_passed_questions
        )

    topic_locked = is_topic_locked(
        topic.order, phase_is_locked, prev_topic_complete, is_admin
    )

    # Get locked questions (questions with >= max_attempts failures in lockout window)
    settings = get_settings()
    lockout_window_start = datetime.now(UTC) - timedelta(
        minutes=settings.quiz_lockout_minutes
    )
    locked_question_map = await question_repo.get_locked_questions(
        user_id=user_id,
        topic_id=topic.id,
        since=lockout_window_start,
        max_attempts=settings.quiz_max_attempts,
    )
    # Convert to list of QuestionLockout, excluding already-passed questions
    # lockout_until = oldest_failure + lockout_minutes (when oldest failure "ages out")
    lockout_duration = timedelta(minutes=settings.quiz_lockout_minutes)
    locked_questions = [
        QuestionLockout(
            question_id=qid,
            lockout_until=oldest_failure + lockout_duration,
            attempts_used=count,
        )
        for qid, (count, oldest_failure) in locked_question_map.items()
        if qid not in passed_question_ids
    ]

    return TopicDetailData(
        id=topic.id,
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        order=topic.order,
        estimated_time=topic.estimated_time,
        is_capstone=topic.is_capstone,
        learning_steps=learning_steps,
        questions=questions,
        learning_objectives=learning_objectives,
        progress=topic_progress,
        completed_step_orders=sorted(completed_steps),
        passed_question_ids=sorted(passed_question_ids),
        locked_questions=locked_questions,
        is_locked=phase_is_locked,
        is_topic_locked=topic_locked,
        previous_topic_name=previous_topic_name,
    )
