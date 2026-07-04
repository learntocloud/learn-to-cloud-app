"""Stats service — assembles the public /stats page payload.

The phase funnel and the graduate list come from a single completion
aggregate (``SubmissionRepository.list_phase_completions``) plus a total
account count and one batched user load. Because phase submissions are
gated on the previous phase, completions are nested (completers of phase
N are a subset of phase N-1), so the funnel is monotone and "graduates"
are simply the learners who appear in every completable phase. The
latest-commit panel is fetched (and cached) separately via the shared
GitHub helper.
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

    # Group completions into a per-phase set of completer ids.
    completers_by_phase: dict[int, set[int]] = {}
    for order, user_id in completions:
        completers_by_phase.setdefault(order, set()).add(user_id)

    # Only phases with at least one requirement are "completable".
    completable_orders = sorted(
        order for order, total in requirement_counts.items() if total > 0
    )

    funnel = [
        PhaseFunnelRow(
            order=order,
            name=phase_names.get(order, f"Phase {order}"),
            count=len(completers_by_phase.get(order, set())),
        )
        for order in completable_orders
    ]

    # Graduates completed every completable phase.
    graduate_ids: set[int] = set()
    if completable_orders:
        graduate_ids = set.intersection(
            *(completers_by_phase.get(order, set()) for order in completable_orders)
        )

    total_accounts = await UserRepository(db).count()

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

    return StatsPageData(
        total_accounts=total_accounts,
        funnel=funnel,
        graduates=graduates,
        repo_updates=repo_updates,
    )
