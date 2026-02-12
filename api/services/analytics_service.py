"""Community analytics service.

Composes raw aggregate queries with content metadata to produce
a privacy-safe analytics payload for the public status page.

ARCHITECTURE:
- A background task (started in main.py lifespan) calls
  refresh_analytics() on a timer to pre-compute the analytics payload.
- The result is persisted to the analytics_snapshot DB table so it
  survives restarts and is consistent across replicas.
- The status page route calls get_community_analytics() which reads
  from a short-lived in-memory cache backed by the DB table.  No
  request ever triggers the 10 aggregate queries directly.
"""

import asyncio
import logging
from datetime import UTC, datetime

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.analytics_repository import AnalyticsRepository
from schemas import (
    CommunityAnalytics,
    DayActivity,
    MonthlyTrend,
    PhaseDistributionItem,
    VerificationStat,
)
from services.content_service import get_all_phases
from services.progress_service import get_phase_requirements

logger = logging.getLogger(__name__)

# Short in-memory cache to avoid hitting the DB on every request.
# The background task refreshes the DB row; this cache avoids redundant
# SELECT on rapid successive requests to the status page.
_LOCAL_CACHE_TTL = 60  # seconds
_local_cache: TTLCache[str, CommunityAnalytics] = TTLCache(
    maxsize=1, ttl=_LOCAL_CACHE_TTL
)

_DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

# Default refresh interval for the background task (1 hour).
REFRESH_INTERVAL_SECONDS = 3600


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
    db: AsyncSession | None = None,
) -> CommunityAnalytics:
    """Read pre-computed analytics.

    Returns the cached result from the analytics_snapshot table.
    If no snapshot exists yet (first startup before background task runs),
    returns a zeroed-out placeholder.  No aggregate queries run here.

    Args:
        db: Optional DB session for reading the snapshot.  If None, returns
            the in-memory cache only (used by callers that don't have a
            session handy).
    """
    # Fast path: in-memory cache hit
    cached = _local_cache.get("analytics")
    if cached is not None:
        return cached

    # Read from DB if session provided
    if db is not None:
        repo = AnalyticsRepository(db)
        row = await repo.get_snapshot_data()
        if row is not None:
            analytics = CommunityAnalytics.model_validate_json(row)
            _local_cache["analytics"] = analytics
            return analytics

    # No snapshot yet — return placeholder
    return _empty_analytics()


def _empty_analytics() -> CommunityAnalytics:
    """Return zeroed-out analytics for when no snapshot exists yet."""
    return CommunityAnalytics(
        total_users=0,
        total_certificates=0,
        active_learners_30d=0,
        completion_rate=0.0,
        phase_distribution=[],
        signup_trends=[],
        certificate_trends=[],
        verification_stats=[],
        activity_by_day=[],
        generated_at=datetime.now(UTC),
    )


async def _compute_analytics(db: AsyncSession) -> CommunityAnalytics:
    """Run aggregate queries and compose the full analytics payload.

    This is called only by the background refresh task — never in a
    request handler.
    """
    repo = AnalyticsRepository(db)

    # Sequential queries — same session/connection, cannot run concurrently
    total_users = await repo.get_total_users()
    total_certificates = await repo.get_total_certificates()
    active_30d = await repo.get_active_learners(days=30)
    histogram = await repo.get_step_completion_histogram()
    signup_raw = await repo.get_signups_by_month()
    cert_raw = await repo.get_certificates_by_month()
    submission_stats = await repo.get_submission_stats_by_phase()
    activity_dow = await repo.get_activity_by_day_of_week()

    # Derive users_reached per phase from the histogram instead of a
    # separate query — the histogram already contains all the data.
    users_reached: dict[int, int] = {}
    for phase_id, _step_count, num_users in histogram:
        users_reached[phase_id] = users_reached.get(phase_id, 0) + num_users

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

    # --- Completion rate ---
    completion_rate = (
        round(total_certificates / total_users * 100, 1) if total_users > 0 else 0.0
    )

    return CommunityAnalytics(
        total_users=total_users,
        total_certificates=total_certificates,
        active_learners_30d=active_30d,
        completion_rate=completion_rate,
        phase_distribution=phase_distribution,
        signup_trends=signup_trends,
        certificate_trends=certificate_trends,
        verification_stats=verification_stats,
        activity_by_day=activity_by_day,
        generated_at=datetime.now(UTC),
    )


async def refresh_analytics(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Compute analytics and persist to the snapshot table.

    Opens its own short-lived session.  Called by the background task
    in main.py and can also be called manually (e.g., from a management
    command after a data import).
    """
    async with session_maker() as db:
        result = await _compute_analytics(db)

        now = datetime.now(UTC)
        data_json = result.model_dump_json()

        repo = AnalyticsRepository(db)
        await repo.upsert_snapshot(data_json, now)
        await db.commit()

    # Update local cache so this replica sees the new data immediately
    _local_cache["analytics"] = result

    logger.info(
        "analytics.refreshed",
        extra={
            "total_users": result.total_users,
            "total_certificates": result.total_certificates,
            "active_30d": result.active_learners_30d,
        },
    )


async def analytics_refresh_loop(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Background loop that refreshes analytics on a timer.

    Runs forever until cancelled.  Failures are logged but do not
    stop the loop — the previous snapshot remains available.
    """
    while True:
        try:
            await refresh_analytics(session_maker)
        except Exception:
            logger.exception("analytics.background_refresh.failed")
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
