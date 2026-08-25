"""Assemble aggregate data for the public community experience."""

import logging
from datetime import timedelta

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_requirement_counts_by_phase,
)
from learn_to_cloud_shared.github_updates import get_latest_curriculum_commits
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.schemas import (
    CommunityActivity,
    CommunityMember,
    CommunityPageData,
    CommunityPhaseActivity,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_community_page_data(db: AsyncSession) -> CommunityPageData:
    """Build the aggregate community page payload."""
    phases = get_curriculum_overview()
    phase_names = {phase.order: phase.name for phase in phases}
    requirement_counts = get_requirement_counts_by_phase()
    catalog = get_curriculum_catalog()
    attempt_repository = VerificationAttemptRepository(db)
    completions = await attempt_repository.list_phase_completions(
        requirement_counts, catalog.phase_order_by_requirement_uuid
    )

    # Group completions into a per-phase set of completer ids.
    completers_by_phase: dict[int, set[int]] = {}
    for order, user_id in completions:
        completers_by_phase.setdefault(order, set()).add(user_id)

    # Only phases with at least one requirement are "completable".
    completable_orders = sorted(
        order for order, total in requirement_counts.items() if total > 0
    )

    activity_rows = await attempt_repository.get_community_activity(
        since=utcnow() - timedelta(days=7),
        phase_order_by_requirement_uuid=catalog.phase_order_by_requirement_uuid,
    )
    total_activity = next(
        (row for row in activity_rows if row.phase_order is None),
        None,
    )
    activity = CommunityActivity(
        active_learners=total_activity.active_learners if total_activity else 0,
        attempts=total_activity.attempts if total_activity else 0,
        projects_verified=total_activity.projects_verified if total_activity else 0,
    )
    phase_activity = [
        CommunityPhaseActivity(
            phase_order=row.phase_order,
            label=phase_names.get(row.phase_order, f"Phase {row.phase_order}"),
            active_learners=row.active_learners,
            attempts=row.attempts,
            projects_verified=row.projects_verified,
        )
        for row in activity_rows
        if row.phase_order is not None
        and (row.active_learners or row.projects_verified)
    ]

    # Graduates completed every completable phase.
    graduate_ids: set[int] = set()
    if completable_orders:
        graduate_ids = set.intersection(
            *(completers_by_phase.get(order, set()) for order in completable_orders)
        )

    users = await UserRepository(db).get_by_ids(graduate_ids)
    graduates = sorted(
        (
            CommunityMember(
                github_username=user.github_username,
                avatar_url=user.avatar_url,
            )
            for user in users
        ),
        key=lambda m: m.github_username.lower(),
    )

    repo_updates = await get_latest_curriculum_commits()

    return CommunityPageData(
        activity=activity,
        phase_activity=phase_activity,
        graduates=graduates,
        repo_updates=repo_updates,
    )
