"""Business metrics for Learn to Cloud.

Tracks verification outcomes via OpenTelemetry counters.
When telemetry is disabled, the OTel API returns no-op instruments (zero overhead).

Usage::

    from core.metrics import VERIFICATION_COUNTER, VERIFICATION_DURATION

    VERIFICATION_COUNTER.add(1, {"submission_type": "CI_STATUS", "result": "pass"})
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("learn_to_cloud")

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
