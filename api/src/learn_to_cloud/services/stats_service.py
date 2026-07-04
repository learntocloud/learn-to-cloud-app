"""Stats service — assembles the public /stats page payload.

The phase funnel and completer lists come from a single completion
aggregate (``SubmissionRepository.list_phase_completions``) plus a total
account count and one batched user load. The latest-commit panel is
fetched (and cached) separately via the shared GitHub helper.
"""

import logging

from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_requirement_counts_by_phase,
)
from learn_to_cloud_shared.github_updates import get_latest_curriculum_commits
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.schemas import (
    CommunityMember,
    PhaseCompleters,
    PhaseFunnelRow,
    StatsPageData,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_stats_page_data(db: AsyncSession) -> StatsPageData:
    """Build the full /stats payload."""
    phases = await get_curriculum_overview(db)
    phase_names = {phase.order: phase.name for phase in phases}

    requirement_counts = await get_requirement_counts_by_phase(db)
    completions = await SubmissionRepository(db).list_phase_completions(
        requirement_counts
    )

    # Group (phase_order, user_id) rows into per-phase completer id lists.
    completer_ids_by_phase: dict[int, list[int]] = {}
    for order, user_id in completions:
        completer_ids_by_phase.setdefault(order, []).append(user_id)

    total_accounts = await UserRepository(db).count()

    # One batched load resolves every completer across all phases.
    all_ids = {uid for ids in completer_ids_by_phase.values() for uid in ids}
    users = await UserRepository(db).get_by_ids(all_ids)
    member_by_id = {
        user.id: CommunityMember(
            github_username=user.github_username,
            avatar_url=user.avatar_url,
        )
        for user in users
    }

    ordered_phases = sorted(phase_names)
    funnel = [
        PhaseFunnelRow(
            order=order,
            name=phase_names[order],
            count=len(completer_ids_by_phase.get(order, [])),
        )
        for order in ordered_phases
    ]

    completers = [
        PhaseCompleters(
            order=order,
            name=phase_names[order],
            members=sorted(
                (
                    member_by_id[uid]
                    for uid in completer_ids_by_phase.get(order, [])
                    if uid in member_by_id
                ),
                key=lambda m: m.github_username.lower(),
            ),
        )
        for order in ordered_phases
    ]

    repo_updates = await get_latest_curriculum_commits()

    return StatsPageData(
        total_accounts=total_accounts,
        funnel=funnel,
        completers=completers,
        repo_updates=repo_updates,
    )
