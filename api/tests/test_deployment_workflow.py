"""Guard the simplified deployment's routing and readiness behavior."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = yaml.load(
    (_ROOT / ".github/workflows/app-deploy.yml").read_text(), Loader=yaml.BaseLoader
)
_JOBS = _WORKFLOW["jobs"]
_STEPS = {step.get("name"): step for step in _JOBS["deploy"]["steps"]}


def test_deployment_job_gates_and_ordering():
    assert set(_JOBS) == {"changes", "quality", "infrastructure", "deploy"}
    assert _JOBS["infrastructure"]["needs"] == ["changes", "quality"]
    assert _JOBS["infrastructure"]["if"] == "needs.changes.outputs.infra == 'true'"
    assert _JOBS["deploy"]["needs"] == ["changes", "quality", "infrastructure"]
    assert " ".join(_JOBS["deploy"]["if"].split()) == (
        "always() && !cancelled() && needs.changes.result == 'success' && "
        "needs.quality.result == 'success' && "
        "(needs.infrastructure.result == 'success' || "
        "needs.infrastructure.result == 'skipped') && "
        "(needs.changes.outputs.app == 'true' || needs.changes.outputs.infra == 'true')"
    )
    app_steps = [
        "Log in to ACR",
        "Set up Docker Buildx",
        "Build API image for validation",
        "Build migrations image for validation",
        "Validate runtime images",
        "Publish API image",
        "Publish migrations image",
        "Run database migrations",
        "Deploy to Container App",
    ]
    assert [
        name
        for name, step in _STEPS.items()
        if step.get("if") == "needs.changes.outputs.app == 'true'"
    ] == app_steps
    assert list(_STEPS)[-2:] == [
        "Verify production readiness",
        "Smoke test verification submit path",
    ]
    assert all("if" not in _STEPS[name] for name in list(_STEPS)[-2:])


@pytest.mark.parametrize(
    ("output", "excluded_target"), [("app", "infrastructure"), ("infra", "application")]
)
def test_manual_targets_override_push_filters(output, excluded_target):
    target = _WORKFLOW["on"]["workflow_dispatch"]["inputs"]["target"]
    assert target["default"] == "application"
    assert target["options"] == ["application", "infrastructure", "all"]
    assert _JOBS["changes"]["outputs"][output] == (
        "${{ github.event_name == 'workflow_dispatch' && "
        f"inputs.target != '{excluded_target}' || "
        "github.event_name != 'workflow_dispatch' && "
        f"steps.filter.outputs.{output} == 'true' }}}}"
    )


_AZ_STUB = """#!/bin/bash
set -eu
case "$*" in
  "containerapp show "*)
    [[ "$*" == *properties.latestRevisionName* ]]
    echo new ;;
  "containerapp revision list "*)
    [[ "$*" == *registry/api:commit* ]]
    echo new ;;
  "containerapp revision show "*)
    [[ "$*" == *"--revision new "* ]]
    printf '{"health":"%s","running":"%s","traffic":%s}' "$HEALTH" "$RUNNING" "$TRAFFIC"
    ;;
  "containerapp logs show "*) ;;
  *) exit 1 ;;
esac
"""


@pytest.mark.parametrize(
    ("artifact", "health", "running", "traffic", "http", "success"),
    [
        ("true", "Healthy", "Running", "100", "200", True),
        ("false", "Healthy", "Running", "100", "200", True),
        ("false", "Unhealthy", "Failed", "0", "200", False),
        ("false", "Healthy", "Running", "0", "200", False),
        ("true", "Healthy", "Running", "100", "503", False),
    ],
)
def test_readiness_gate(tmp_path, artifact, health, running, traffic, http, success):
    for name, body in {
        "az": _AZ_STUB,
        "sleep": "#!/bin/sh\nexit 0\n",
        "curl": '#!/bin/sh\nprintf "%s" "$HTTP_CODE"\n',
    }.items():
        executable = tmp_path / name
        executable.write_text(body)
        executable.chmod(0o700)
    result = subprocess.run(
        ["bash", "-c", _STEPS["Verify production readiness"]["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "APP_NAME": "api",
            "RESOURCE_GROUP": "resource-group",
            "READY_URL": "https://example.invalid/ready",
            "REGISTRY": "registry",
            "GITHUB_SHA": "commit",
            "ARTIFACT_DEPLOYED": artifact,
            "HEALTH": health,
            "RUNNING": running,
            "TRAFFIC": traffic,
            "HTTP_CODE": http,
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
