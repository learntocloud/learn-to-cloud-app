"""Dashboard service.

This module provides dashboard data by combining:
- Static content from JSON files
- User progress from the database

Source of truth: .github/skills/progression-system/progression-system.md
"""

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.cache import get_cached_steps_by_topic, set_cached_steps_by_topic
from models import Submission
from repositories.progress_repository import StepProgressRepository
from repositories.submission_repository import SubmissionRepository
from schemas import (
    BadgeData,
    DashboardData,
    HandsOnSubmissionResponse,
    Phase,
    PhaseDetailData,
    PhaseProgressData,
    PhaseSummaryData,
    Topic,
    TopicDetailData,
    TopicProgressData,
    TopicSummaryData,
    UserSummaryData,
)
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
    phase_progress_to_data,
)

logger = get_logger(__name__)


async def _get_steps_by_topic(db: AsyncSession, user_id: str) -> dict[str, set[int]]:
    """Get all completed steps grouped by topic, with caching.

    Avoids re-scanning step_progress when fetch_user_progress already
    queried the same table for aggregate counts.
    TTL matches the progress cache (60s).
    """
    cached = get_cached_steps_by_topic(user_id)
    if cached is not None:
        return cached

    step_repo = StepProgressRepository(db)
    result = await step_repo.get_all_completed_by_user(user_id)
    set_cached_steps_by_topic(user_id, result)
    return result


def _build_phase_summary(
    phase: Phase,
    progress_data: PhaseProgressData | None,
) -> PhaseSummaryData:
    """Build PhaseSummaryData from a Phase and computed values."""
    return PhaseSummaryData(
        id=phase.id,
        name=phase.name,
        slug=phase.slug,
        description=phase.description,
        short_description=phase.short_description,
        order=phase.order,
        topics_count=len(phase.topics),
        objectives=list(phase.objectives),
        capstone=phase.capstone,
        hands_on_verification=phase.hands_on_verification,
        progress=progress_data,
    )


def _build_topic_summary(
    topic: Topic,
    progress: TopicProgressData | None,
) -> TopicSummaryData:
    """Build TopicSummaryData from a Topic and computed values."""
    return TopicSummaryData(
        id=topic.id,
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        order=topic.order,
        is_capstone=topic.is_capstone,
        steps_count=len(topic.learning_steps),
        progress=progress,
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
    """Get complete dashboard data for a user."""
    phases = get_all_phases()
    user_progress = await fetch_user_progress(db, user_id)

    phase_summaries: list[PhaseSummaryData] = []
    for phase in phases:
        progress = user_progress.phases.get(phase.id)
        progress_data = phase_progress_to_data(progress) if progress else None
        phase_summaries.append(_build_phase_summary(phase, progress_data))

    overall_percentage = user_progress.overall_percentage
    phases_completed = user_progress.phases_completed
    current_phase = user_progress.current_phase

    phase_completion_counts = get_phase_completion_counts(user_progress)

    earned_badges = compute_all_badges(
        phase_completion_counts=phase_completion_counts,
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
) -> list[PhaseSummaryData]:
    """Get all phases with progress for a user.

    If user_id is None (unauthenticated), no progress data is shown.
    """
    phases = get_all_phases()

    if user_id is None:
        return [_build_phase_summary(phase, None) for phase in phases]

    user_progress = await fetch_user_progress(db, user_id)

    return [
        _build_phase_summary(
            phase,
            phase_progress_to_data(progress)
            if (progress := user_progress.phases.get(phase.id))
            else None,
        )
        for phase in phases
    ]


async def get_phase_detail(
    db: AsyncSession,
    user_id: str | None,
    phase_slug: str,
) -> PhaseDetailData | None:
    """Get detailed phase info with topics and progress."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None

    if user_id is None:
        topic_summaries: list[TopicSummaryData] = []
        for topic in phase.topics:
            topic_summaries.append(_build_topic_summary(topic, None))

        hands_on_reqs = get_requirements_for_phase(phase.id)

        return PhaseDetailData(
            id=phase.id,
            name=phase.name,
            slug=phase.slug,
            description=phase.description,
            short_description=phase.short_description,
            order=phase.order,
            objectives=list(phase.objectives),
            capstone=phase.capstone,
            hands_on_verification=phase.hands_on_verification,
            topics=topic_summaries,
            progress=None,
            hands_on_requirements=list(hands_on_reqs),
            hands_on_submissions=[],
            all_hands_on_validated=False,
            is_phase_complete=False,
        )

    user_progress = await fetch_user_progress(db, user_id)
    phase_progress = user_progress.phases.get(phase.id)

    # Batch queries to avoid N+1 (2 queries instead of 2*N)
    all_steps_by_topic = await _get_steps_by_topic(db, user_id)

    phase_topic_ids = {topic.id for topic in phase.topics}
    steps_by_topic: dict[str, set[int]] = {
        tid: steps
        for tid, steps in all_steps_by_topic.items()
        if tid in phase_topic_ids
    }

    topic_summaries: list[TopicSummaryData] = []

    for topic in phase.topics:
        completed_steps = steps_by_topic.get(topic.id, set())
        topic_progress = compute_topic_progress(topic, completed_steps)

        topic_summaries.append(_build_topic_summary(topic, topic_progress))

    # Get hands-on requirements and submissions
    hands_on_reqs = get_requirements_for_phase(phase.id)
    submission_repo = SubmissionRepository(db)
    db_submissions = await submission_repo.get_by_user_and_phase(user_id, phase.id)
    hands_on_submissions = [_to_hands_on_submission_data(sub) for sub in db_submissions]

    progress_data = phase_progress_to_data(phase_progress) if phase_progress else None

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
        order=phase.order,
        objectives=list(phase.objectives),
        capstone=phase.capstone,
        hands_on_verification=phase.hands_on_verification,
        topics=topic_summaries,
        progress=progress_data,
        hands_on_requirements=list(hands_on_reqs),
        hands_on_submissions=hands_on_submissions,
        all_hands_on_validated=all_hands_on_validated,
        is_phase_complete=is_phase_complete,
    )


async def get_topic_detail(
    db: AsyncSession,
    user_id: str | None,
    phase_slug: str,
    topic_slug: str,
) -> TopicDetailData | None:
    """Get detailed topic info with steps and progress."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None

    topic = get_topic_by_slugs(phase_slug, topic_slug)
    if not topic:
        return None

    learning_steps = list(topic.learning_steps)
    learning_objectives = list(topic.learning_objectives)

    if user_id is None:
        return TopicDetailData(
            id=topic.id,
            slug=topic.slug,
            name=topic.name,
            description=topic.description,
            order=topic.order,
            is_capstone=topic.is_capstone,
            learning_steps=learning_steps,
            learning_objectives=learning_objectives,
            progress=None,
            completed_step_orders=[],
        )

    # Use cached steps-by-topic (avoids re-scanning step_progress)
    all_steps_by_topic = await _get_steps_by_topic(db, user_id)

    completed_steps = all_steps_by_topic.get(topic.id, set())

    topic_progress = compute_topic_progress(topic, completed_steps)

    return TopicDetailData(
        id=topic.id,
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        order=topic.order,
        is_capstone=topic.is_capstone,
        learning_steps=learning_steps,
        learning_objectives=learning_objectives,
        progress=topic_progress,
        completed_step_orders=sorted(completed_steps),
    )
