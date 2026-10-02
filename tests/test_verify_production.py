"""Guard the production verification script's image and readiness gates."""

import os
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_production.sh"

_AZ_STUB = """#!/bin/bash
set -eu
case "$*" in
  "containerapp show "*)
    printf '{"revision":"new","image":"%s"}' "$LATEST_IMAGE" ;;
  "containerapp revision show "*)
    [[ "$*" == *"--revision new "* ]]
    printf '{"health":"%s","running":"%s","traffic":%s}' "$HEALTH" "$RUNNING" "$TRAFFIC"
    ;;
  "containerapp logs show "*) ;;
  *) exit 1 ;;
esac
"""


@pytest.mark.parametrize(
    ("latest_image", "health", "running", "traffic", "http", "success"),
    [
        ("registry/api:commit", "Healthy", "Running", "100", "200", True),
        ("registry/api:other", "Healthy", "Running", "100", "200", False),
        ("registry/api:commit", "Unhealthy", "Failed", "0", "200", False),
        ("registry/api:commit", "Healthy", "Running", "0", "200", False),
        ("registry/api:commit", "Healthy", "Running", "100", "503", False),
    ],
)
def test_verify_production(
    tmp_path, latest_image, health, running, traffic, http, success
):
    for name, body in {
        "az": _AZ_STUB,
        "sleep": "#!/bin/sh\nexit 0\n",
        "curl": '#!/bin/sh\nprintf "%s" "$HTTP_CODE"\n',
    }.items():
        executable = tmp_path / name
        executable.write_text(body)
        executable.chmod(0o700)
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "APP_NAME": "api",
            "RESOURCE_GROUP": "resource-group",
            "API_URL": "https://example.invalid",
            "EXPECTED_IMAGE": "registry/api:commit",
            "LATEST_IMAGE": latest_image,
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
