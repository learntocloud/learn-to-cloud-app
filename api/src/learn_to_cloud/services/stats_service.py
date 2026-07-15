"""Stats service — assembles the public /stats page payload.

The phase funnel and the graduate list come from a single completion
aggregate (``VerificationAttemptRepository.list_phase_completions``) plus a
total account count and one batched user load. Because phase submissions
are gated on the previous phase, completions are nested (completers of
phase N are a subset of phase N-1), so the funnel is monotone and
"graduates" are simply the learners who appear in every completable phase.
The latest-commit panel is fetched (and cached) separately via the shared
GitHub helper.

Completions come from succeeded ``verification_attempts``; stats stay
verification-only and do not count learning steps.
"""

import logging

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_requirement_counts_by_phase,
)
from learn_to_cloud_shared.github_updates import get_latest_curriculum_commits
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.schemas import (
    CommunityMember,
    FunnelLevel,
    StatsPageData,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_stats_page_data(db: AsyncSession) -> StatsPageData:
    """Build the full /stats payload."""
    phases = get_curriculum_overview()
    phase_names = {phase.order: phase.name for phase in phases}

    requirement_counts = get_requirement_counts_by_phase()
    phase_order_by_requirement_uuid = (
        get_curriculum_catalog().phase_order_by_requirement_uuid
    )
    completions = await VerificationAttemptRepository(db).list_phase_completions(
        requirement_counts, phase_order_by_requirement_uuid
    )

    # Group completions into a per-phase set of completer ids.
    completers_by_phase: dict[int, set[int]] = {}
    for order, user_id in completions:
        completers_by_phase.setdefault(order, set()).add(user_id)

    # Only phases with at least one requirement are "completable".
    completable_orders = sorted(
        order for order, total in requirement_counts.items() if total > 0
    )

    total_accounts = await UserRepository(db).count()

    # Build the funnel top-down: total accounts, then each phase, tracking
    # both share of total (bar width) and conversion from the level above.
    funnel: list[FunnelLevel] = [
        FunnelLevel(
            label="Total accounts",
            count=total_accounts,
            pct_of_total=100.0,
            pct_of_previous=None,
            is_total=True,
        )
    ]
    prev_count = total_accounts
    for order in completable_orders:
        count = len(completers_by_phase.get(order, set()))
        funnel.append(
            FunnelLevel(
                label=f"Phase {order}: {phase_names.get(order, order)}",
                count=count,
                pct_of_total=(count / total_accounts * 100) if total_accounts else 0.0,
                pct_of_previous=(count / prev_count * 100) if prev_count else None,
            )
        )
        prev_count = count

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

    return StatsPageData(
        total_accounts=total_accounts,
        funnel=funnel,
        graduates=graduates,
        repo_updates=repo_updates,
    )
