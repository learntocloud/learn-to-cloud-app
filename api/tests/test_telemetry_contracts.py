"""Static contracts for production telemetry and Azure Monitor alerts."""

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parents[2]
_PYTHON_TELEMETRY_ROOTS = (
    _ROOT / "api" / "src",
    _ROOT / "apps" / "verification-functions",
    _ROOT / "packages" / "learn-to-cloud-shared" / "src" / "learn_to_cloud_shared",
)

_ALLOWED_APPLICATION_ATTRIBUTES = {
    "auth.configuration.reason",
    "auth.identity.reason",
    "content.artifact.hash",
    "content.artifact_schema.version",
    "content.curriculum.version",
    "content.phase.slug",
    "content.requirement.slug",
    "content.topic.slug",
    "database.schema.current_revision",
    "database.schema.expected_revision",
    "error.type",
    "github.repository",
    "http.response.status_code",
    "http.target",
    "http.url",
    "startup.initialized",
    "telemetry.configuration.reason",
    "url.full",
    "url.path",
    "url.query",
    "verification.attempt.age_seconds",
    "verification.attempt.created",
    "verification.attempt.id",
    "verification.check.name",
    "verification.deployed_api.ai_verified",
    "verification.deployed_api.challenge_verified",
    "verification.deployed_api.verified",
    "verification.durable.status",
    "verification.error.code",
    "verification.failure.kind",
    "verification.failure.stage",
    "verification.operation",
    "verification.outcome",
    "verification.reason",
    "verification.reconciler.candidate_count",
    "verification.reconciler.stuck_count",
    "verification.reconciler.terminalized_count",
    "verification.requirement.slug",
    "verification.step.result",
    "verification.stuck.reason",
    "verification.task.id",
    "verification.terminal.source",
    "verification.terminal.write_won",
}

_PROHIBITED_APPLICATION_ATTRIBUTES = {
    "attempt_age_seconds",
    "attempt_created",
    "attempt_id",
    "candidate_count",
    "cas_won",
    "code_head",
    "content_hash",
    "cutoff",
    "db_head",
    "durable_status",
    "error",
    "error_code",
    "error_type",
    "failure_kind",
    "github_username",
    "display_name",
    "first_name",
    "last_name",
    "user.display_name",
    "user.first_name",
    "user.last_name",
    "hint",
    "orchestrator_name",
    "outcome",
    "path",
    "phase_slug",
    "reason",
    "repo",
    "requirement_slug",
    "runtime_status",
    "status",
    "status_code",
    "stuck_count",
    "stuck_reason",
    "terminal_source",
    "terminalized_count",
    "topic_slug",
    "user_id",
}


def _resource_block(source: str, resource_name: str) -> str:
    start = source.index(
        f'resource "azurerm_monitor_scheduled_query_rules_alert_v2" "{resource_name}"'
    )
    next_resource = source.find("\nresource ", start + 1)
    return source[start:] if next_resource == -1 else source[start:next_resource]


def _dict_keys(
    node: ast.AST | None,
    bindings: dict[str, set[str]],
) -> set[str] | None:
    if not isinstance(node, ast.Dict):
        if isinstance(node, ast.Name):
            return bindings.get(node.id)
        return None
    keys = {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    return keys if len(keys) == len(node.keys) else None


def _application_attribute_names() -> tuple[set[str], list[str]]:
    attributes: set[str] = set()
    unresolved: list[str] = []
    log_methods = {"critical", "debug", "error", "exception", "info", "warning"}

    for root in _PYTHON_TELEMETRY_ROOTS:
        for path in root.rglob("*.py"):
            if ".venv" in path.parts:
                continue
            tree = ast.parse(path.read_text())
            bindings: dict[str, set[str]] = {}
            log_aliases: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name):
                        keys = _dict_keys(node.value, bindings)
                        if keys is not None:
                            bindings.setdefault(node.target.id, set()).update(keys)
                    continue
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        candidates = (
                            (node.value.body, node.value.orelse)
                            if isinstance(node.value, ast.IfExp)
                            else (node.value,)
                        )
                        if any(
                            isinstance(candidate, ast.Attribute)
                            and candidate.attr in log_methods
                            for candidate in candidates
                        ):
                            log_aliases.add(target.id)
                        keys = _dict_keys(node.value, bindings)
                        if keys is not None:
                            bindings.setdefault(target.id, set()).update(keys)
                    elif (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)
                    ):
                        bindings.setdefault(target.value.id, set()).add(
                            target.slice.value
                        )

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                extra_keywords = [
                    keyword for keyword in node.keywords if keyword.arg == "extra"
                ]
                if name in log_methods or name in log_aliases:
                    for keyword in extra_keywords:
                        keys = _dict_keys(keyword.value, bindings)
                        if keys is None:
                            unresolved.append(f"{path}:{node.lineno}:log extra")
                        else:
                            attributes.update(keys)
                elif name == "set_attribute" and node.args:
                    attribute = node.args[0]
                    if isinstance(attribute, ast.Constant) and isinstance(
                        attribute.value, str
                    ):
                        attributes.add(attribute.value)
                elif name == "set_attributes" and node.args:
                    keys = _dict_keys(node.args[0], bindings)
                    if keys is None:
                        unresolved.append(f"{path}:{node.lineno}:span attributes")
                    else:
                        attributes.update(keys)
                elif name == "add_event" and len(node.args) > 1:
                    keys = _dict_keys(node.args[1], bindings)
                    if keys is None:
                        unresolved.append(f"{path}:{node.lineno}:span event")
                    else:
                        attributes.update(keys)
                elif name in {"start_as_current_span", "start_span"}:
                    for keyword in node.keywords:
                        if keyword.arg == "attributes":
                            keys = _dict_keys(keyword.value, bindings)
                            if keys is None:
                                unresolved.append(
                                    f"{path}:{node.lineno}:span attributes"
                                )
                            else:
                                attributes.update(keys)
                elif name in {"add", "record"} and len(node.args) > 1:
                    keys = _dict_keys(node.args[1], bindings)
                    if keys is None:
                        unresolved.append(f"{path}:{node.lineno}:metric attributes")
                    else:
                        attributes.update(keys)

    return attributes, unresolved


def _exception_log_events() -> set[str]:
    events: set[str] = set()
    for root in _PYTHON_TELEMETRY_ROOTS:
        for path in root.rglob("*.py"):
            if ".venv" in path.parts:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "exception"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    events.add(node.args[0].value)
    return events


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


def test_application_owned_attributes_match_the_canonical_schema():
    emitted, unresolved = _application_attribute_names()

    assert unresolved == []
    assert emitted == _ALLOWED_APPLICATION_ATTRIBUTES
    assert emitted.isdisjoint(_PROHIBITED_APPLICATION_ATTRIBUTES)


def test_raw_exception_details_are_limited_to_application_boundaries():
    assert _exception_log_events() == {
        "init.failed",
        "init.timeout",
        "unhandled.exception",
    }


def test_application_code_does_not_explicitly_record_raw_span_exceptions():
    calls: list[str] = []
    for root in _PYTHON_TELEMETRY_ROOTS:
        for path in root.rglob("*.py"):
            if ".venv" in path.parts:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "record_exception"
                ):
                    calls.append(f"{path}:{node.lineno}")

    assert calls == []


def test_frontend_telemetry_uses_only_bounded_properties():
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
    assert "window.location.pathname" not in script
    assert "requestConfig.path" not in script
    assert "data-telemetry-route" in template
    assert "disableExceptionTracking: true" in template
    assert "enableUnhandledPromiseRejectionTracking: false" in template
    assert "delete baseData.refUri" in script
    assert "'navigation.type'" in script
    assert "'http.request.method'" in script
    assert "'htmx.boosted'" in script
    assert "navigationType" not in script
    assert "statusCode" not in script
    assert "htmx:responseError" not in script
    assert "htmx:sendError" in script


def test_frontend_initializer_removes_urls_and_tracks_same_route_navigation():
    script = (
        _ROOT
        / "api"
        / "src"
        / "learn_to_cloud"
        / "static"
        / "js"
        / "frontend-telemetry.js"
    )
    test_script = f"""
const fs = require('fs');
const tracked = [];
const listeners = {{}};
let initializer = null;
let marker = {{
  getAttribute: () => '/phase/{{phase_slug}}'
}};
global.window = {{
  location: {{ origin: 'https://learntocloud.guide' }},
  appInsights: {{
    addTelemetryInitializer: (value) => {{ initializer = value; }},
    trackEvent: (value) => tracked.push(value),
    trackPageView: (value) => tracked.push(value)
  }}
}};
global.document = {{
  title: 'Phase',
  querySelector: () => marker,
  addEventListener: (name, callback) => {{ listeners[name] = callback; }}
}};
eval(fs.readFileSync({str(script)!r}, 'utf8'));
const item = {{
  baseType: 'PageviewData',
  baseData: {{
    uri: 'https://learntocloud.guide/phase/1?token=secret',
    refUri: 'https://example.com/private?token=secret'
  }}
}};
initializer(item);
listeners['htmx:afterSettle']({{ detail: {{ boosted: true }} }});
listeners['htmx:afterSettle']({{ detail: {{ boosted: false }} }});
marker = null;
listeners['htmx:historyRestore']();
console.log(JSON.stringify({{ item, tracked }}));
"""
    result = subprocess.run(
        ["node", "-e", test_script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert "refUri" not in payload["item"]["baseData"]
    assert (
        payload["item"]["baseData"]["uri"]
        == "https://learntocloud.guide/phase/{phase_slug}"
    )
    assert [item["properties"]["navigation.type"] for item in payload["tracked"]] == [
        "initial",
        "htmx",
        "history",
    ]
    assert payload["tracked"][2]["uri"] == "https://learntocloud.guide/unmatched"


def test_stuck_alert_uses_only_canonical_attributes():
    monitoring = (_ROOT / "infra" / "monitoring.tf").read_text()
    runbook = (_ROOT / "docs" / "runbooks" / "alerts.md").read_text()
    block = _resource_block(monitoring, "verification_attempt_stuck")

    for canonical in (
        "verification.durable.status",
        "verification.attempt.age_seconds",
        "verification.stuck.reason",
    ):
        assert f'customDimensions["{canonical}"]' in block
        assert f'customDimensions["{canonical}"]' in runbook

    for historical in ("durable_status", "attempt_age_seconds", "stuck_reason"):
        assert f'customDimensions["{historical}"]' not in block
        assert f'customDimensions["{historical}"]' not in runbook
