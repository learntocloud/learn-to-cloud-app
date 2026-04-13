"""Custom business metrics for Learn to Cloud.

Exposes counters and histograms for key domain events so they appear
alongside the auto-instrumented infrastructure meters in Aspire / Azure
Monitor.

Metrics are created lazily via ``opentelemetry.metrics.get_meter()`` which
resolves against the global ``MeterProvider`` set up by
``core.observability``.  If telemetry is disabled the OTel API returns
no-op instruments — zero overhead.

Usage in services::

    from core.metrics import VERIFICATION_COUNTER, VERIFICATION_DURATION

    VERIFICATION_COUNTER.add(1, {"submission_type": "CI_STATUS", "result": "pass"})
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("learn_to_cloud")

# ── Step completion metrics ───────────────────────────────────────────

STEP_COMPLETED_COUNTER = _meter.create_counter(
    name="step.completed",
    description="Learning steps marked as complete",
    unit="{step}",
)

STEP_UNCOMPLETED_COUNTER = _meter.create_counter(
    name="step.uncompleted",
    description="Learning steps marked as incomplete",
    unit="{step}",
)

# ── Verification metrics ──────────────────────────────────────────────

VERIFICATION_COUNTER = _meter.create_counter(
    name="verification.attempt",
    description="Number of hands-on verification attempts",
    unit="{attempt}",
)

VERIFICATION_DURATION = _meter.create_histogram(
    name="verification.duration",
    description="Time taken to complete a verification attempt",
    unit="s",
)

# ── Auth metrics ──────────────────────────────────────────────────────

AUTH_LOGIN_COUNTER = _meter.create_counter(
    name="auth.login",
    description="OAuth login attempts",
    unit="{attempt}",
)

# ── Submission constraint metrics ─────────────────────────────────────

SUBMISSION_DAILY_LIMIT_COUNTER = _meter.create_counter(
    name="submission.daily_limit_exceeded",
    description="Submissions rejected by daily cap",
    unit="{rejection}",
)

# ── LLM token usage metrics ───────────────────────────────────────────

LLM_TOKEN_COUNTER = _meter.create_counter(
    name="llm.token.usage",
    description="LLM tokens consumed by verification workflows",
    unit="{token}",
)

# ── User lifecycle metrics ────────────────────────────────────────────

USER_DELETION_COUNTER = _meter.create_counter(
    name="user.deletion",
    description="User account deletions",
    unit="{deletion}",
)
