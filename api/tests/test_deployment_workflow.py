"""Deployment routing and production gates stay intact when jobs are combined."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = yaml.load(
    (_ROOT / ".github/workflows/app-deploy.yml").read_text(), Loader=yaml.BaseLoader
)
_JOBS = _WORKFLOW["jobs"]
_APP_ONLY = "needs.changes.outputs.app == 'true'"


def _condition(
    expression: str, values: dict[str, str], *, cancelled: bool = False
) -> bool:
    """Execute the workflow's string comparisons and boolean operators in Bash."""
    expression = expression.removeprefix("${{").removesuffix("}}").strip()
    expression = expression.replace("always()", "'true' == 'true'")
    expression = expression.replace("!cancelled()", "\"$CANCELLED\" != 'true'")
    variables = {}
    for index, (name, value) in enumerate(values.items()):
        variable = f"VALUE_{index}"
        expression = expression.replace(name, f'"${variable}"')
        variables[variable] = value
    result = subprocess.run(
        ["bash", "-c", f"[[ {expression} ]]"],
        env={**os.environ, "CANCELLED": str(cancelled).lower(), **variables},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


@pytest.mark.parametrize(
    ("event", "target", "app_changed", "infra_changed", "app", "infra"),
    [
        ("push", "", "true", "false", True, False),
        ("push", "", "false", "true", False, True),
        ("push", "", "true", "true", True, True),
        ("push", "", "false", "false", False, False),
        ("workflow_dispatch", "application", "false", "true", True, False),
        ("workflow_dispatch", "infrastructure", "true", "false", False, True),
        ("workflow_dispatch", "all", "false", "false", True, True),
    ],
)
def test_deployment_targets(event, target, app_changed, infra_changed, app, infra):
    values = {
        "github.event_name": event,
        "inputs.target": target,
        "steps.filter.outputs.app": app_changed,
        "steps.filter.outputs.infra": infra_changed,
    }
    outputs = _JOBS["changes"]["outputs"]
    assert _condition(outputs["app"], values) is app
    assert _condition(outputs["infra"], values) is infra
    assert (
        _condition(
            _JOBS["infrastructure"]["if"],
            {"needs.changes.outputs.infra": str(infra).lower()},
        )
        is infra
    )


@pytest.mark.parametrize(
    ("app", "infra", "infra_result", "quality_result", "stop_result", "expected"),
    [
        ("true", "false", "skipped", "success", "success", True),
        ("false", "true", "success", "success", "success", True),
        ("true", "true", "success", "success", "success", True),
        ("false", "false", "skipped", "success", "skipped", False),
        ("true", "true", "failure", "success", "success", False),
        ("true", "true", "cancelled", "success", "success", False),
        ("true", "false", "skipped", "failure", "success", False),
        ("true", "false", "skipped", "skipped", "success", False),
        ("true", "false", "skipped", "success", "failure", False),
    ],
)
def test_deployment_prerequisites(
    app, infra, infra_result, quality_result, stop_result, expected
):
    assert set(_JOBS["deploy"]["needs"]) == {
        "changes",
        "quality",
        "stop_legacy_verification",
        "infrastructure",
    }
    assert (
        _condition(
            _JOBS["deploy"]["if"],
            {
                "needs.changes.result": "success",
                "needs.changes.outputs.app": app,
                "needs.changes.outputs.infra": infra,
                "needs.quality.result": quality_result,
                "needs.stop_legacy_verification.result": stop_result,
                "needs.infrastructure.result": infra_result,
            },
        )
        is expected
    )


@pytest.mark.parametrize(
    ("changes_result", "cancelled"),
    [("failure", False), ("skipped", False), ("success", True)],
)
def test_deploy_stops_on_failed_change_detection_or_cancellation(
    changes_result, cancelled
):
    assert not _condition(
        _JOBS["deploy"]["if"],
        {
            "needs.changes.result": changes_result,
            "needs.changes.outputs.app": "true",
            "needs.changes.outputs.infra": "false",
            "needs.quality.result": "success",
            "needs.stop_legacy_verification.result": "success",
            "needs.infrastructure.result": "skipped",
        },
        cancelled=cancelled,
    )


def test_infra_only_never_builds_migrates_or_updates_the_api():
    steps = _JOBS["deploy"]["steps"]
    app_steps = {
        "Log in to ACR",
        "Set up Docker Buildx",
        "Build API image for validation",
        "Build migrations image for validation",
        "Validate runtime images",
        "Publish API image",
        "Publish migrations image",
        "Run database migrations",
        "Deploy to Container App",
    }
    assert {step["name"] for step in steps if step.get("if") == _APP_ONLY} == app_steps
    names = [step.get("name") for step in steps]
    assert names.index("Validate runtime images") < names.index("Publish API image")
    assert names.index("Publish migrations image") < names.index(
        "Run database migrations"
    )
    assert names.index("Run database migrations") < names.index(
        "Deploy to Container App"
    )
    assert names.index("Deploy to Container App") < names.index(
        "Verify production readiness"
    )
    for step in steps:
        if step.get("name") in {
            "Verify production readiness",
            "Smoke test verification submit path",
        }:
            # Default success() stops after a failed deployment.
            assert "if" not in step
    assert sum(step.get("uses", "").startswith("azure/login@") for step in steps) == 1
    assert not {"preflight", "deployment_context", "verify_production"} & _JOBS.keys()


def test_deployment_step_outputs_have_no_dangling_job_references():
    steps = _JOBS["deploy"]["steps"]
    context = next(step for step in steps if step.get("id") == "context")
    published = set(re.findall(r"^publish_output (\w+) ", context["run"], re.MULTILINE))
    referenced = set(re.findall(r"steps\.context\.outputs\.(\w+)", json.dumps(steps)))
    assert referenced <= published
    assert "needs.deployment_context" not in json.dumps(_WORKFLOW)
    assert "needs.deploy_app" not in json.dumps(_WORKFLOW)


@pytest.mark.parametrize(
    ("ref", "environment", "subscription", "success"),
    [
        ("refs/heads/main", "dev", "subscription", True),
        ("refs/heads/feature", "dev", "subscription", False),
        ("refs/heads/main", "", "subscription", False),
        ("refs/heads/main", "dev", "", False),
    ],
)
def test_preflight_still_blocks_invalid_deployments(
    ref, environment, subscription, success
):
    result = subprocess.run(
        ["bash", "-c", _JOBS["changes"]["steps"][0]["run"]],
        env={
            **os.environ,
            "GITHUB_REF": ref,
            "AZURE_ENV_NAME": environment,
            "AZURE_SUBSCRIPTION_ID": subscription,
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert (result.returncode == 0) is success, result.stderr


_AZ_STUB = """\
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["CALLS"]).open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
if args[:2] == ["containerapp", "show"]:
    assert args[args.index("--query") + 1] == "properties.latestRevisionName"
    print("api--infra-revision")
elif args[:3] == ["containerapp", "revision", "list"]:
    assert "registry/api:commit" in args[args.index("--query") + 1]
    print("api--app-revision")
elif args[:3] == ["containerapp", "revision", "show"]:
    revision = args[args.index("--revision") + 1]
    expected = (
        "api--app-revision" if os.environ["ARTIFACT_DEPLOYED"] == "true"
        else "api--infra-revision"
    )
    assert revision == expected
    print(json.dumps({
        "health": os.environ["HEALTH"],
        "running": os.environ["RUNNING"],
        "traffic": int(os.environ["TRAFFIC"]),
    }))
elif args[:3] == ["containerapp", "logs", "show"]:
    print("diagnostic logs")
else:
    sys.exit("Unexpected Azure command")
"""


@pytest.mark.parametrize(
    ("artifact", "health", "running", "traffic", "http_code", "success"),
    [
        ("true", "Healthy", "Running", "100", "200", True),
        ("false", "Healthy", "Running", "100", "200", True),
        ("false", "Unhealthy", "Failed", "0", "200", False),
        ("false", "Healthy", "Running", "0", "200", False),
        ("true", "Healthy", "Running", "100", "503", False),
    ],
)
def test_readiness_checks_the_expected_revision(
    tmp_path, artifact, health, running, traffic, http_code, success
):
    script = next(
        step["run"]
        for step in _JOBS["deploy"]["steps"]
        if step.get("name") == "Verify production readiness"
    )
    for name, body in {
        "az": f"#!{sys.executable}\n{_AZ_STUB}",
        "sleep": "#!/bin/sh\nexit 0\n",
        "curl": '#!/bin/sh\nprintf "%s" "$HTTP_CODE"\n',
    }.items():
        executable = tmp_path / name
        executable.write_text(body)
        executable.chmod(0o700)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CALLS": str(calls),
            "APP_NAME": "api",
            "RESOURCE_GROUP": "resource-group",
            "READY_URL": "https://example.invalid/ready",
            "REGISTRY": "registry",
            "GITHUB_SHA": "commit",
            "ARTIFACT_DEPLOYED": artifact,
            "HEALTH": health,
            "RUNNING": running,
            "TRAFFIC": traffic,
            "HTTP_CODE": http_code,
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    assert any(
        command[:3] == ["containerapp", "revision", "show"] for command in commands
    )
