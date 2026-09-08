"""Contracts for alert signals and browser telemetry."""

import json
import re
import subprocess
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
        / "packages/learn-to-cloud-shared/src/learn_to_cloud_shared"
        / "core/observability.py"
    ).read_text()
    assert 'name  = "OTEL_TRACES_SAMPLER"' in container_app
    assert 'value = "microsoft.rate_limited"' in container_app
    assert 'name  = "OTEL_TRACES_SAMPLER_ARG"' in container_app
    assert "enable_trace_based_sampling_for_logs=False" in observability


def test_frontend_initializer_keeps_paths_without_query_credentials():
    script = _ROOT / "api/src/learn_to_cloud/static/js/frontend-telemetry.js"
    test_script = f"""
const calls = [];
const listeners = {{}};
let initializer;
global.document = {{
  addEventListener: (name, callback) => {{ listeners[name] = callback; }}
}};
global.window = {{
  location: {{ origin: 'https://learntocloud.guide' }},
  appInsights: {{
    addTelemetryInitializer: value => {{ initializer = value; calls.push('init'); }},
    loadAppInsights: () => calls.push('load'),
    trackPageView: () => calls.push('page')
  }}
}};
require({str(script)!r});
const url = 'https://user:password@example.com/normal/path?token=secret#secret';
const items = [
  {{ baseType: 'PageviewData', baseData: {{ uri: url, refUri: url }} }},
  {{ baseType: 'PageviewPerformanceData', baseData: {{ uri: url }} }},
  {{ baseType: 'RemoteDependencyData',
     baseData: {{ target: url, name: 'GET /normal/path?token=secret' }} }},
  {{ baseType: 'ExceptionData',
     data: {{ url, errorSrc: 'window.onerror@' + url }},
     baseData: {{
       properties: {{ url, errorSrc: 'window.onerror@' + url }},
       exceptions: [{{ message: 'Script failed' }}]
     }} }},
  {{ baseType: 'EventData', baseData: {{ name: 'action' }} }}
];
items.forEach(initializer);
listeners['htmx:afterSettle']({{ detail: {{ boosted: false }} }});
listeners['htmx:afterSettle']({{ detail: {{ boosted: true }} }});
listeners['htmx:historyRestore']();
console.log(JSON.stringify({{ items, calls }}));
"""
    result = subprocess.run(
        ["node", "-e", test_script], check=True, capture_output=True, text=True
    )
    payload = json.loads(result.stdout)
    assert payload["calls"] == ["init", "load", "page", "page", "page"]
    page, performance, dependency, exception, event = payload["items"]
    url = "https://example.com/normal/path"
    assert page["baseData"] == {"uri": url, "refUri": url}
    assert performance["baseData"]["uri"] == url
    assert dependency["baseData"] == {"target": url, "name": "GET /normal/path"}
    assert exception["baseData"]["properties"]["url"] == url
    assert "errorSrc" not in exception["baseData"]["properties"]
    assert exception["data"] == {"url": url}
    assert exception["baseData"]["exceptions"] == [{"message": "Script failed"}]
    assert event["baseData"]["name"] == "action"
    assert "secret" not in result.stdout
    assert "password" not in result.stdout


def test_stuck_alert_uses_only_canonical_attributes():
    monitoring = (_ROOT / "infra" / "monitoring.tf").read_text()
    runbook = (_ROOT / "docs" / "runbooks" / "alerts.md").read_text()
    block = _resource_block(monitoring, "verification_attempt_stuck")
    for canonical in (
        "verification.attempt.age_seconds",
        "verification.stuck.reason",
    ):
        assert f'customDimensions["{canonical}"]' in block
        assert f'customDimensions["{canonical}"]' in runbook
    for historical in ("durable_status", "attempt_age_seconds", "stuck_reason"):
        assert f'customDimensions["{historical}"]' not in block
        assert f'customDimensions["{historical}"]' not in runbook
    assert "DurableStatus" not in block
    assert "verification.durable.status" not in block
    assert "union traces, exceptions" in block
    assert "coalesce(message, outerMessage)" in block
    assert '"verification.worker.failed"' in block
    assert 'Event == "verification.worker.failed" or isnotempty(AttemptId)' in block
    assert 'cloud_RoleName == "learn-to-cloud-api"' in block
    for reason in ("queued_beyond_limit", "execution_beyond_limit", "worker_failed"):
        assert f'"{reason}"' in block
        assert reason in runbook


def test_verification_alerts_use_only_the_api_role():
    monitoring = (_ROOT / "infra" / "monitoring.tf").read_text()
    for name in (
        "verification_attempt_system_error",
        "verification_llm_immediate_failure",
        "verification_llm_transient_failure",
        "verification_attempt_stuck",
    ):
        block = _resource_block(monitoring, name)
        assert 'cloud_RoleName == "learn-to-cloud-api"' in block
        assert "functions" not in block
    assert 'outerMessage == "unhandled.exception"' in _resource_block(
        monitoring, "api_unhandled_exception"
    )
