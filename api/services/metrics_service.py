"""Metrics aggregation service for trend analysis.

This module provides:
- Daily metrics aggregation from raw event tables
- Trend data retrieval for admin dashboards
- Backfill capability for historical data

Metrics are stored in daily_metrics table for fast queries.
Aggregation runs nightly via scheduled job or on-demand.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.telemetry import log_metric, track_operation
from models import DailyMetrics
from repositories.metrics_repository import MetricsRepository
from schemas import DailyMetricsData, TrendsResponse, TrendSummary

logger = get_logger(__name__)


# =============================================================================
# Domain Exceptions
# =============================================================================


class InvalidDateRangeError(Exception):
    """Raised when end_date is before start_date."""

    def __init__(self, start_date: date, end_date: date) -> None:
        self.start_date = start_date
        self.end_date = end_date
        super().__init__(f"Invalid date range: {start_date} to {end_date}")


class BackfillRangeTooLargeError(Exception):
    """Raised when backfill date range exceeds maximum allowed days."""

    def __init__(self, days_requested: int, max_days: int = 365) -> None:
        self.days_requested = days_requested
        self.max_days = max_days
        super().__init__(
            f"Backfill range of {days_requested} days exceeds maximum of {max_days}"
        )


@track_operation("metrics_aggregation")
async def aggregate_daily_metrics(
    db: AsyncSession,
    target_date: date,
) -> DailyMetrics:
    """Aggregate and store metrics for a single day.

    Queries raw event tables and computes:
    - active_users: Distinct users with any activity
    - new_signups: Users created on this date
    - returning_users: Active users minus new signups
    - steps_completed: Learning steps marked done
    - questions_attempted: Total question attempts
    - questions_passed: Passed question attempts
    - hands_on_submitted: Submissions created
    - hands_on_validated: Submissions validated
    - phases_completed: Phase completion events
    - certificates_earned: Certificates issued
    - question_pass_rate: passed/attempted (0-100)

    Args:
        db: Database session
        target_date: The date to aggregate

    Returns:
        The created/updated DailyMetrics record
    """
    repo = MetricsRepository(db)

    # Run all counts (could parallelize with asyncio.gather for perf)
    active_users = await repo.count_active_users(target_date)
    new_signups = await repo.count_new_signups(target_date)
    returning_users = max(0, active_users - new_signups)

    steps_completed = await repo.count_steps_completed(target_date)
    questions_attempted = await repo.count_questions_attempted(target_date)
    questions_passed = await repo.count_questions_passed(target_date)
    hands_on_submitted = await repo.count_hands_on_submitted(target_date)
    hands_on_validated = await repo.count_hands_on_validated(target_date)
    phases_completed = await repo.count_phases_completed(target_date)
    certificates_earned = await repo.count_certificates_earned(target_date)

    # Compute pass rate
    question_pass_rate = 0.0
    if questions_attempted > 0:
        question_pass_rate = round((questions_passed / questions_attempted) * 100, 2)

    metrics = DailyMetrics(
        metric_date=target_date,
        active_users=active_users,
        new_signups=new_signups,
        returning_users=returning_users,
        steps_completed=steps_completed,
        questions_attempted=questions_attempted,
        questions_passed=questions_passed,
        hands_on_submitted=hands_on_submitted,
        hands_on_validated=hands_on_validated,
        phases_completed=phases_completed,
        certificates_earned=certificates_earned,
        question_pass_rate=question_pass_rate,
    )

    result = await repo.upsert_metrics(metrics)

    log_metric("metrics.aggregated", 1, {"date": target_date.isoformat()})
    logger.info(
        "metrics.aggregated",
        date=target_date.isoformat(),
        active_users=active_users,
        new_signups=new_signups,
    )

    return result


async def backfill_metrics(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    max_days: int = 365,
) -> int:
    """Backfill metrics for a date range.

    Useful for:
    - Initial setup (backfill historical data)
    - Recovering from data issues
    - Re-aggregating after schema changes

    Args:
        db: Database session
        start_date: First date to aggregate (inclusive)
        end_date: Last date to aggregate (inclusive)
        max_days: Maximum allowed days in range (default 365)

    Returns:
        Number of days aggregated

    Raises:
        InvalidDateRangeError: If end_date < start_date
        BackfillRangeTooLargeError: If range exceeds max_days
    """
    if end_date < start_date:
        raise InvalidDateRangeError(start_date, end_date)

    days_requested = (end_date - start_date).days + 1
    if days_requested > max_days:
        raise BackfillRangeTooLargeError(days_requested, max_days)

    days_aggregated = 0
    current = start_date

    while current <= end_date:
        await aggregate_daily_metrics(db, current)
        days_aggregated += 1
        current += timedelta(days=1)

    logger.info(
        "metrics.backfill_complete",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        days_aggregated=days_aggregated,
    )

    return days_aggregated


async def get_trends(
    db: AsyncSession,
    days: int = 30,
) -> TrendsResponse:
    """Get trend data for admin dashboard.

    Args:
        db: Database session
        days: Number of days of history to return

    Returns:
        TrendsResponse with daily metrics and summary statistics
    """
    repo = MetricsRepository(db)

    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=days - 1)

    metrics = await repo.get_metrics_range(start_date, today)

    # Convert to response schema
    daily_data = [
        DailyMetricsData(
            date=m.metric_date,
            active_users=m.active_users,
            new_signups=m.new_signups,
            returning_users=m.returning_users,
            steps_completed=m.steps_completed,
            questions_attempted=m.questions_attempted,
            questions_passed=m.questions_passed,
            hands_on_submitted=m.hands_on_submitted,
            hands_on_validated=m.hands_on_validated,
            phases_completed=m.phases_completed,
            certificates_earned=m.certificates_earned,
            question_pass_rate=m.question_pass_rate,
        )
        for m in metrics
    ]

    # Compute summary statistics
    total_active = sum(d.active_users for d in daily_data)
    total_signups = sum(d.new_signups for d in daily_data)
    total_steps = sum(d.steps_completed for d in daily_data)
    total_questions = sum(d.questions_attempted for d in daily_data)
    total_passed = sum(d.questions_passed for d in daily_data)
    total_phases = sum(d.phases_completed for d in daily_data)
    total_certs = sum(d.certificates_earned for d in daily_data)

    avg_daily_active = total_active / len(daily_data) if daily_data else 0
    overall_pass_rate = (
        round((total_passed / total_questions) * 100, 2) if total_questions > 0 else 0
    )

    # Compute week-over-week change for active users
    if len(daily_data) >= 14:
        this_week = sum(d.active_users for d in daily_data[:7])
        last_week = sum(d.active_users for d in daily_data[7:14])
        wow_change = (
            round(((this_week - last_week) / last_week) * 100, 1)
            if last_week > 0
            else 0
        )
    else:
        wow_change = 0

    # Get cumulative totals
    total_users = await repo.get_total_users()
    total_certificates = await repo.get_total_certificates()

    summary = TrendSummary(
        period_days=days,
        total_active_users=total_active,
        avg_daily_active_users=round(avg_daily_active, 1),
        total_new_signups=total_signups,
        total_steps_completed=total_steps,
        total_questions_attempted=total_questions,
        total_questions_passed=total_passed,
        overall_pass_rate=overall_pass_rate,
        total_phases_completed=total_phases,
        total_certificates_earned=total_certs,
        active_users_wow_change=wow_change,
        cumulative_users=total_users,
        cumulative_certificates=total_certificates,
    )

    return TrendsResponse(
        days=daily_data,
        summary=summary,
        start_date=start_date,
        end_date=today,
    )
