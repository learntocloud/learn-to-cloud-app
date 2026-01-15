"""Dashboard service.

This module provides dashboard data by combining:
- Static content from JSON files
- User progress from the database
- Locking logic based on the progression system

Source of truth: .github/skills/progression-system/SKILL.md
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.progress import QuestionAttemptRepository, StepProgressRepository
from repositories.submission import SubmissionRepository
from schemas import (
    BadgeResponse,
    DashboardResponse,
    HandsOnRequirement,
    HandsOnSubmissionResponse,
    LearningObjectiveSchema,
    PhaseDetailSchema,
    PhaseProgressSchema,
    PhaseSummarySchema,
    TopicDetailSchema,
    TopicProgressSchema,
    TopicSummarySchema,
    UserSummarySchema,
)
from services.activity import get_streak_data
from services.badges import compute_all_badges
from services.content import (
    Phase,
    Topic,
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_slugs,
)
from services.hands_on_verification import get_requirements_for_phase
from services.progress import (
    PHASE_REQUIREMENTS,
    PhaseProgress,
    fetch_user_progress,
    get_phase_completion_counts,
)
from services.submissions import get_validated_ids_by_phase

logger = logging.getLogger(__name__)


def _compute_topic_progress(
    topic: Topic,
    completed_steps: set[int],
    passed_question_ids: set[str],
) -> TopicProgressSchema:
    """Compute progress for a single topic.

    Topic Progress = (Steps Completed + Questions Passed) / (Total Steps + Total Questions)
    """
    steps_completed = len(completed_steps)
    steps_total = len(topic.learning_steps)
    questions_passed = len(passed_question_ids)
    questions_total = len(topic.questions)

    total = steps_total + questions_total
    completed = steps_completed + questions_passed

    if total == 0:
        percentage = 100.0
        status = "completed"
    else:
        percentage = (completed / total) * 100
        if steps_completed >= steps_total and questions_passed >= questions_total:
            status = "completed"
        elif completed > 0:
            status = "in_progress"
        else:
            status = "not_started"

    return TopicProgressSchema(
        steps_completed=steps_completed,
        steps_total=steps_total,
        questions_passed=questions_passed,
        questions_total=questions_total,
        percentage=round(percentage, 1),
        status=status,
    )


def _is_topic_complete(topic: Topic, completed_steps: set[int], passed_question_ids: set[str]) -> bool:
    """Check if a topic is complete (all steps + all questions)."""
    return (
        len(completed_steps) >= len(topic.learning_steps)
        and len(passed_question_ids) >= len(topic.questions)
    )


def _phase_progress_to_schema(progress: PhaseProgress) -> PhaseProgressSchema:
    """Convert PhaseProgress dataclass to schema."""
    if progress.is_complete:
        status = "completed"
    elif (
        progress.steps_completed > 0
        or progress.questions_passed > 0
        or progress.hands_on_validated_count > 0
    ):
        status = "in_progress"
    else:
        status = "not_started"

    return PhaseProgressSchema(
        steps_completed=progress.steps_completed,
        steps_required=progress.steps_required,
        questions_passed=progress.questions_passed,
        questions_required=progress.questions_required,
        hands_on_validated=progress.hands_on_validated_count,
        hands_on_required=progress.hands_on_required_count,
        percentage=round(progress.overall_percentage, 1),
        status=status,
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
) -> DashboardResponse:
    """Get complete dashboard data for a user.

    This is the main entry point for dashboard data. It:
    1. Loads all phases from content
    2. Fetches user progress from database
    3. Computes phase/topic completion status
    4. Determines locking based on progression rules

    Locking rules from SKILL.md:
    - Phase 0: Always unlocked
    - Phases 1-6: Previous phase must be complete
    - Admin users: Bypass all locks
    """
    phases = get_all_phases()
    user_progress = await fetch_user_progress(db, user_id)

    phase_summaries: list[PhaseSummarySchema] = []
    prev_phase_complete = True  # Phase 0 is always "unlocked"

    for phase in phases:
        progress = user_progress.phases.get(phase.id)
        progress_schema = _phase_progress_to_schema(progress) if progress else None

        # Locking logic
        if is_admin:
            is_locked = False
        elif phase.id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        phase_summaries.append(
            PhaseSummarySchema(
                id=phase.id,
                name=phase.name,
                slug=phase.slug,
                description=phase.description,
                short_description=phase.short_description,
                estimated_weeks=phase.estimated_weeks,
                order=phase.order,
                topics_count=len(phase.topics),
                progress=progress_schema,
                is_locked=is_locked,
            )
        )

        # Update for next iteration
        prev_phase_complete = progress.is_complete if progress else False

    # Calculate overall stats
    overall_percentage = user_progress.overall_percentage
    phases_completed = user_progress.phases_completed
    current_phase = user_progress.current_phase

    # Compute badges
    phase_completion_counts = get_phase_completion_counts(user_progress)
    
    # Get streak for streak badges
    streak_data = await get_streak_data(db, user_id)
    
    earned_badges = compute_all_badges(
        phase_completion_counts=phase_completion_counts,
        longest_streak=streak_data.longest_streak,
    )
    badges = [
        BadgeResponse(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
        )
        for badge in earned_badges
    ]

    return DashboardResponse(
        user=UserSummarySchema(
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
) -> list[PhaseSummarySchema]:
    """Get all phases with progress for a user.
    
    If user_id is None (unauthenticated):
    - No progress data
    - Only Phase 0 is unlocked
    """
    phases = get_all_phases()
    
    # For unauthenticated users, no progress data
    if user_id is None:
        return [
            PhaseSummarySchema(
                id=phase.id,
                name=phase.name,
                slug=phase.slug,
                description=phase.description,
                short_description=phase.short_description,
                estimated_weeks=phase.estimated_weeks,
                order=phase.order,
                topics_count=len(phase.topics),
                progress=None,
                is_locked=(phase.id != 0),  # Only phase 0 unlocked for visitors
            )
            for phase in phases
        ]
    
    user_progress = await fetch_user_progress(db, user_id)

    phase_summaries: list[PhaseSummarySchema] = []
    prev_phase_complete = True

    for phase in phases:
        progress = user_progress.phases.get(phase.id)
        progress_schema = _phase_progress_to_schema(progress) if progress else None

        if is_admin:
            is_locked = False
        elif phase.id == 0:
            is_locked = False
        else:
            is_locked = not prev_phase_complete

        phase_summaries.append(
            PhaseSummarySchema(
                id=phase.id,
                name=phase.name,
                slug=phase.slug,
                description=phase.description,
                short_description=phase.short_description,
                estimated_weeks=phase.estimated_weeks,
                order=phase.order,
                topics_count=len(phase.topics),
                progress=progress_schema,
                is_locked=is_locked,
            )
        )

        prev_phase_complete = progress.is_complete if progress else False

    return phase_summaries


async def get_phase_detail(
    db: AsyncSession,
    user_id: str | None,
    phase_slug: str,
    is_admin: bool,
) -> PhaseDetailSchema | None:
    """Get detailed phase info with topics and progress.

    Topic locking rules from SKILL.md:
    - First topic in phase: Always unlocked (if phase is unlocked)
    - Subsequent topics: Previous topic must be complete
    - Admin users: Bypass all locks
    
    For unauthenticated users:
    - No progress data
    - First topic unlocked (if phase is Phase 0)
    - Other topics locked
    """
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None

    # For unauthenticated users
    if user_id is None:
        # Only Phase 0 is accessible
        phase_is_locked = phase.id != 0
        
        topic_summaries: list[TopicSummarySchema] = []
        for topic in phase.topics:
            # Only first topic unlocked for Phase 0
            topic_is_locked = phase_is_locked or topic.order != 1
            
            topic_summaries.append(
                TopicSummarySchema(
                    id=topic.id,
                    slug=topic.slug,
                    name=topic.name,
                    description=topic.description,
                    order=topic.order,
                    estimated_time=topic.estimated_time,
                    is_capstone=topic.is_capstone,
                    steps_count=len(topic.learning_steps),
                    questions_count=len(topic.questions),
                    progress=None,
                    is_locked=topic_is_locked,
                )
            )
        
        # Get hands-on requirements (but no submissions for unauthenticated)
        hands_on_reqs = get_requirements_for_phase(phase.id)
        
        return PhaseDetailSchema(
            id=phase.id,
            name=phase.name,
            slug=phase.slug,
            description=phase.description,
            short_description=phase.short_description,
            estimated_weeks=phase.estimated_weeks,
            order=phase.order,
            objectives=list(phase.objectives),
            topics=topic_summaries,
            progress=None,
            hands_on_requirements=[
                HandsOnRequirement(
                    id=r.id,
                    phase_id=r.phase_id,
                    submission_type=r.submission_type,
                    name=r.name,
                    description=r.description,
                    example_url=r.example_url,
                )
                for r in hands_on_reqs
            ],
            hands_on_submissions=[],
            is_locked=phase_is_locked,
        )

    # Get user progress for this phase and previous phase
    user_progress = await fetch_user_progress(db, user_id)
    phase_progress = user_progress.phases.get(phase.id)

    # Check if this phase is locked
    if is_admin:
        phase_is_locked = False
    elif phase.id == 0:
        phase_is_locked = False
    else:
        prev_progress = user_progress.phases.get(phase.id - 1)
        phase_is_locked = not (prev_progress and prev_progress.is_complete)

    # Get step and question progress for topics
    step_repo = StepProgressRepository(db)
    question_repo = QuestionAttemptRepository(db)

    # Fetch all topic progress data
    steps_by_topic: dict[str, set[int]] = {}
    questions_by_topic: dict[str, set[str]] = {}

    for topic in phase.topics:
        steps_by_topic[topic.id] = await step_repo.get_completed_step_orders(user_id, topic.id)
        questions_by_topic[topic.id] = await question_repo.get_passed_question_ids(user_id, topic.id)

    # Build topic summaries with locking
    topic_summaries: list[TopicSummarySchema] = []
    prev_topic_complete = True

    for topic in phase.topics:
        completed_steps = steps_by_topic.get(topic.id, set())
        passed_questions = questions_by_topic.get(topic.id, set())

        topic_progress = _compute_topic_progress(topic, completed_steps, passed_questions)

        # Topic locking
        if is_admin:
            topic_is_locked = False
        elif phase_is_locked:
            topic_is_locked = True
        elif topic.order == 1:
            topic_is_locked = False
        else:
            topic_is_locked = not prev_topic_complete

        topic_summaries.append(
            TopicSummarySchema(
                id=topic.id,
                slug=topic.slug,
                name=topic.name,
                description=topic.description,
                order=topic.order,
                estimated_time=topic.estimated_time,
                is_capstone=topic.is_capstone,
                steps_count=len(topic.learning_steps),
                questions_count=len(topic.questions),
                progress=topic_progress,
                is_locked=topic_is_locked,
            )
        )

        prev_topic_complete = _is_topic_complete(topic, completed_steps, passed_questions)

    # Get hands-on requirements and submissions
    hands_on_reqs = get_requirements_for_phase(phase.id)
    submission_repo = SubmissionRepository(db)
    db_submissions = await submission_repo.get_by_user_and_phase(user_id, phase.id)
    hands_on_submissions = [
        HandsOnSubmissionResponse.model_validate(sub) for sub in db_submissions
    ]

    progress_schema = _phase_progress_to_schema(phase_progress) if phase_progress else None

    return PhaseDetailSchema(
        id=phase.id,
        name=phase.name,
        slug=phase.slug,
        description=phase.description,
        short_description=phase.short_description,
        estimated_weeks=phase.estimated_weeks,
        order=phase.order,
        objectives=list(phase.objectives),
        topics=topic_summaries,
        progress=progress_schema,
        hands_on_requirements=list(hands_on_reqs),
        hands_on_submissions=hands_on_submissions,
        is_locked=phase_is_locked,
    )


async def get_topic_detail(
    db: AsyncSession,
    user_id: str | None,
    phase_slug: str,
    topic_slug: str,
    is_admin: bool,
) -> TopicDetailSchema | None:
    """Get detailed topic info with steps, questions, and progress.

    Includes locking status and previous topic name for UI messaging.
    
    For unauthenticated users:
    - No progress data
    - Content is viewable but not interactive
    """
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None

    topic = get_topic_by_slugs(phase_slug, topic_slug)
    if not topic:
        return None

    # Import schemas
    from schemas import LearningStepSchema, QuestionSchema, SecondaryLinkSchema, ProviderOptionSchema

    # Build learning steps and questions (same for all users)
    learning_steps = [
        LearningStepSchema(
            order=s.order,
            text=s.text,
            action=s.action,
            title=s.title,
            url=s.url,
            description=s.description,
            code=s.code,
            secondary_links=[
                SecondaryLinkSchema(text=link.text, url=link.url)
                for link in s.secondary_links
            ],
            options=[
                ProviderOptionSchema(
                    provider=opt.provider,
                    title=opt.title,
                    url=opt.url,
                    description=opt.description,
                )
                for opt in s.options
            ],
        )
        for s in topic.learning_steps
    ]

    questions = [
        QuestionSchema(
            id=q.id,
            prompt=q.prompt,
            expected_concepts=list(q.expected_concepts),
        )
        for q in topic.questions
    ]

    # For unauthenticated users
    if user_id is None:
        phase_is_locked = phase.id != 0
        topic_is_locked = phase_is_locked or topic.order != 1
        
        # Get previous topic name for UI
        topic_index = next((i for i, t in enumerate(phase.topics) if t.id == topic.id), 0)
        previous_topic_name = phase.topics[topic_index - 1].name if topic_index > 0 else None
        
        return TopicDetailSchema(
            id=topic.id,
            slug=topic.slug,
            name=topic.name,
            description=topic.description,
            order=topic.order,
            estimated_time=topic.estimated_time,
            is_capstone=topic.is_capstone,
            learning_steps=learning_steps,
            questions=questions,
            learning_objectives=[
                LearningObjectiveSchema(id=obj.id, text=obj.text, order=obj.order)
                for obj in topic.learning_objectives
            ],
            progress=None,
            completed_step_orders=[],
            passed_question_ids=[],
            is_locked=phase_is_locked,
            is_topic_locked=topic_is_locked,
            previous_topic_name=previous_topic_name,
        )

    # Get user progress
    user_progress = await fetch_user_progress(db, user_id)
    phase_progress = user_progress.phases.get(phase.id)

    # Check phase locking
    if is_admin:
        phase_is_locked = False
    elif phase.id == 0:
        phase_is_locked = False
    else:
        prev_progress = user_progress.phases.get(phase.id - 1)
        phase_is_locked = not (prev_progress and prev_progress.is_complete)

    # Get step and question progress
    step_repo = StepProgressRepository(db)
    question_repo = QuestionAttemptRepository(db)

    completed_steps = await step_repo.get_completed_step_orders(user_id, topic.id)
    passed_question_ids = await question_repo.get_passed_question_ids(user_id, topic.id)

    topic_progress = _compute_topic_progress(topic, completed_steps, passed_question_ids)

    # Check topic locking
    topic_index = next((i for i, t in enumerate(phase.topics) if t.id == topic.id), 0)
    previous_topic_name: str | None = None
    topic_is_locked = False

    if not is_admin and not phase_is_locked and topic_index > 0:
        prev_topic = phase.topics[topic_index - 1]
        previous_topic_name = prev_topic.name

        prev_completed_steps = await step_repo.get_completed_step_orders(user_id, prev_topic.id)
        prev_passed_questions = await question_repo.get_passed_question_ids(user_id, prev_topic.id)

        if not _is_topic_complete(prev_topic, prev_completed_steps, prev_passed_questions):
            topic_is_locked = True

    return TopicDetailSchema(
        id=topic.id,
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        order=topic.order,
        estimated_time=topic.estimated_time,
        is_capstone=topic.is_capstone,
        learning_steps=learning_steps,
        questions=questions,
        learning_objectives=[
            LearningObjectiveSchema(id=obj.id, text=obj.text, order=obj.order)
            for obj in topic.learning_objectives
        ],
        progress=topic_progress,
        completed_step_orders=sorted(completed_steps),
        passed_question_ids=sorted(passed_question_ids),
        is_locked=phase_is_locked,
        is_topic_locked=topic_is_locked,
        previous_topic_name=previous_topic_name,
    )
