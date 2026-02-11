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

    VERIFICATION_COUNTER.add(1, {"submission_type": "CODE_ANALYSIS", "result": "pass"})
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

# ── Certificate metrics ───────────────────────────────────────────────

CERTIFICATE_CREATED_COUNTER = _meter.create_counter(
    name="certificate.created",
    description="Certificates successfully issued",
    unit="{certificate}",
)

CERTIFICATE_CREATION_FAILED_COUNTER = _meter.create_counter(
    name="certificate.creation_failed",
    description="Certificate creation attempts that were rejected",
    unit="{attempt}",
)

CERTIFICATE_VERIFIED_COUNTER = _meter.create_counter(
    name="certificate.verified",
    description="Certificate verification lookups",
    unit="{lookup}",
)
