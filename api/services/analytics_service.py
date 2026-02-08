"""Community analytics service.

Composes raw aggregate queries with content metadata to produce
a privacy-safe analytics payload for public dashboards and
conference storytelling.

CACHING:
- Results are cached for 5 minutes (TTLCache, per-worker).
- Only one cache entry since the data is global, not per-user.
"""

import asyncio
import logging
from datetime import UTC, datetime

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.analytics_repository import AnalyticsRepository
from schemas import (
    CommunityAnalytics,
    DayActivity,
    MonthlyTrend,
    PhaseDistributionItem,
    TopicEngagement,
    VerificationStat,
)
from services.content_service import get_all_phases, get_topic_by_id
from services.progress_service import get_phase_requirements

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes
_cache: TTLCache[str, CommunityAnalytics] = TTLCache(maxsize=1, ttl=_CACHE_TTL)
_cache_lock = asyncio.Lock()

_DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}


def _build_cumulative_trends(
    monthly_counts: list[tuple[str, int]],
) -> list[MonthlyTrend]:
    """Convert raw monthly counts into trends with cumulative totals."""
    trends: list[MonthlyTrend] = []
    cumulative = 0
    for month, count in monthly_counts:
        cumulative += count
        trends.append(MonthlyTrend(month=month, count=count, cumulative=cumulative))
    return trends


def _compute_users_completed_steps(
    histogram: list[tuple[int, int, int]],
    phase_id: int,
    required_steps: int,
) -> int:
    """Count users who completed all reading steps in a phase.

    Uses the step completion histogram to sum users whose step_count
    meets or exceeds the required threshold.
    """
    total = 0
    for h_phase_id, step_count, num_users in histogram:
        if h_phase_id == phase_id and step_count >= required_steps:
            total += num_users
    return total


async def get_community_analytics(
    db: AsyncSession,
) -> CommunityAnalytics:
    """Build the full community analytics payload.

    Runs multiple aggregate queries concurrently and composes the
    results with content metadata. Cached for 5 minutes.

    Warning:
        Queries are run sequentially because they share an AsyncSession.
        asyncpg connections do not support concurrent use on a single
        connection.
    """
    async with _cache_lock:
        cached = _cache.get("analytics")
        if cached is not None:
            return cached

    repo = AnalyticsRepository(db)

    # Sequential queries — same session/connection, cannot run concurrently
    total_users = await repo.get_total_users()
    total_certificates = await repo.get_total_certificates()
    active_30d = await repo.get_active_learners(days=30)
    users_reached = await repo.get_users_reached_per_phase()
    histogram = await repo.get_step_completion_histogram()
    signup_raw = await repo.get_signups_by_month()
    cert_raw = await repo.get_certificates_by_month()
    submission_stats = await repo.get_submission_stats_by_phase()
    activity_dow = await repo.get_activity_by_day_of_week()
    top_topics_raw = await repo.get_top_topics(limit=10)

    # --- Phase distribution (funnel) ---
    phases = get_all_phases()
    phase_distribution: list[PhaseDistributionItem] = []
    for phase in sorted(phases, key=lambda p: p.order):
        requirements = get_phase_requirements(phase.id)
        required_steps = requirements.steps if requirements else 0
        completed_steps = _compute_users_completed_steps(
            histogram, phase.id, required_steps
        )
        phase_distribution.append(
            PhaseDistributionItem(
                phase_id=phase.id,
                phase_name=phase.name,
                users_reached=users_reached.get(phase.id, 0),
                users_completed_steps=completed_steps,
            )
        )

    # --- Trends ---
    signup_trends = _build_cumulative_trends(signup_raw)
    certificate_trends = _build_cumulative_trends(cert_raw)

    # --- Verification stats ---
    verification_stats: list[VerificationStat] = []
    phase_name_map = {p.id: p.name for p in phases}
    for phase_id in sorted(submission_stats.keys()):
        total_attempts, successful = submission_stats[phase_id]
        pass_rate = (successful / total_attempts * 100) if total_attempts > 0 else 0.0
        verification_stats.append(
            VerificationStat(
                phase_id=phase_id,
                phase_name=phase_name_map.get(phase_id, f"Phase {phase_id}"),
                total_attempts=total_attempts,
                successful=successful,
                pass_rate=round(pass_rate, 1),
            )
        )

    # --- Activity by day of week ---
    activity_by_day: list[DayActivity] = []
    for iso_day in range(1, 8):
        activity_by_day.append(
            DayActivity(
                day_name=_DAY_NAMES[iso_day],
                completions=activity_dow.get(iso_day, 0),
            )
        )

    # --- Top topics ---
    top_topics: list[TopicEngagement] = []
    for topic_id, phase_id, active_users in top_topics_raw:
        topic = get_topic_by_id(topic_id)
        topic_name = topic.name if topic else topic_id
        top_topics.append(
            TopicEngagement(
                topic_id=topic_id,
                topic_name=topic_name,
                phase_id=phase_id,
                active_users=active_users,
            )
        )

    # --- Completion rate ---
    completion_rate = (
        round(total_certificates / total_users * 100, 1) if total_users > 0 else 0.0
    )

    result = CommunityAnalytics(
        total_users=total_users,
        total_certificates=total_certificates,
        active_learners_30d=active_30d,
        completion_rate=completion_rate,
        phase_distribution=phase_distribution,
        signup_trends=signup_trends,
        certificate_trends=certificate_trends,
        verification_stats=verification_stats,
        activity_by_day=activity_by_day,
        top_topics=top_topics,
        generated_at=datetime.now(UTC),
    )

    async with _cache_lock:
        _cache["analytics"] = result

    logger.info(
        "analytics.computed",
        extra={
            "total_users": total_users,
            "total_certificates": total_certificates,
            "active_30d": active_30d,
        },
    )

    return result
