"""Static contracts for production telemetry and Azure Monitor alerts."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parents[2]


def _resource_block(source: str, resource_name: str) -> str:
    start = source.index(
        f'resource "azurerm_monitor_scheduled_query_rules_alert_v2" "{resource_name}"'
    )
    next_resource = source.find("\nresource ", start + 1)
    return source[start:] if next_resource == -1 else source[start:next_resource]


def test_every_alert_has_a_documented_signal_contract():
    monitoring = (_ROOT / "infra" / "monitoring.tf").read_text()
    runbook = (_ROOT / "docs" / "runbooks" / "alerts.md").read_text()

    scheduled_alerts = set(
        re.findall(
            r'resource "azurerm_monitor_scheduled_query_rules_alert_v2" "([^"]+)"',
            monitoring,
        )
    )
    expected = {
        "api_unhandled_exception",
        "api_telemetry_pipeline_failure",
        "verification_attempt_system_error",
        "verification_llm_immediate_failure",
        "verification_llm_transient_failure",
        "verification_attempt_stuck",
        "schema_drift",
    }

    assert scheduled_alerts == expected
    assert "`availability`" in runbook
    for alert in expected:
        assert f"`{alert}`" in runbook


def test_telemetry_alert_uses_only_the_app_owned_setup_signal():
    monitoring = (_ROOT / "infra" / "monitoring.tf").read_text()
    block = _resource_block(monitoring, "api_telemetry_pipeline_failure")

    assert 'tostring(ParsedLog.event) == "telemetry.configure.failed"' in block
    assert "azure.monitor.opentelemetry.exporter" not in block
    assert "Envelopes could not be exported" not in block


def test_api_trace_sampling_policy_is_explicit_and_alert_logs_are_unsampled():
    container_app = (_ROOT / "infra" / "container-apps.tf").read_text()
    observability = (
        _ROOT
        / "packages"
        / "learn-to-cloud-shared"
        / "src"
        / "learn_to_cloud_shared"
        / "core"
        / "observability.py"
    ).read_text()

    assert 'name  = "OTEL_TRACES_SAMPLER"' in container_app
    assert 'value = "microsoft.rate_limited"' in container_app
    assert 'name  = "OTEL_TRACES_SAMPLER_ARG"' in container_app
    assert "enable_trace_based_sampling_for_logs=False" in observability


def test_frontend_telemetry_does_not_capture_query_strings_or_request_paths():
    script = (
        _ROOT
        / "api"
        / "src"
        / "learn_to_cloud"
        / "static"
        / "js"
        / "frontend-telemetry.js"
    ).read_text()
    template = (
        _ROOT / "api" / "src" / "learn_to_cloud" / "templates" / "base.html"
    ).read_text()

    assert "window.location.href" not in script
    assert "requestConfig.path" not in script
    assert "uri: window.location.origin + window.location.pathname" in template
    assert "htmx:responseError" not in script
    assert "htmx:sendError" in script
