"""Exercise the deployed stop script against ARM's nested state response."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_FUNCTION_ID = (
    "/subscriptions/test/resourceGroups/rg-ltc-dev"
    "/providers/Microsoft.Web/sites/func-ltc-verification-dev"
)
_AZ_STUB = """\
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
calls = Path(os.environ["CALLS"])
with calls.open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
if args[:2] == ["resource", "list"]:
    if os.environ["FAIL"] == "lookup":
        sys.exit(1)
    print(os.environ["FUNCTION_ID"])
elif args[:2] == ["functionapp", "stop"]:
    sys.exit(1 if os.environ["FAIL"] == "stop" else 0)
elif args[:3] == ["rest", "--method", "get"]:
    if os.environ["FAIL"] == "read":
        sys.exit(1)
    expected_url = (
        "https://management.azure.com" + os.environ["FUNCTION_ID"]
        + "?api-version=2024-04-01"
    )
    assert args[args.index("--url") + 1] == expected_url
    states = json.loads(os.environ["STATES"])
    reads = sum(
        json.loads(line)[:1] == ["rest"]
        for line in calls.read_text().splitlines()
    )
    payload = {"properties": {"state": states[min(reads - 1, len(states) - 1)]}}
    value = payload
    for field in args[args.index("--query") + 1].split("."):
        value = value.get(field, {}) if isinstance(value, dict) else {}
    if isinstance(value, str):
        print(value)
else:
    sys.exit("Unexpected Azure command")
"""


@pytest.mark.parametrize(
    ("states", "failure", "present", "success", "message"),
    [
        (["Stopped"], "", True, True, "is stopped"),
        (["Running", "Stopped"], "", True, True, "is stopped"),
        (["Running"], "", True, False, "did not stop"),
        ([""], "", True, False, "did not return the Function App state"),
        (["Stopped"], "", False, True, "is absent"),
        (["Stopped"], "lookup", True, False, ""),
        (["Stopped"], "stop", True, False, ""),
        (["Stopped"], "read", True, False, ""),
    ],
)
def test_stop_script(tmp_path, states, failure, present, success, message):
    workflow = yaml.safe_load((_ROOT / ".github/workflows/app-deploy.yml").read_text())
    script = next(
        step["run"]
        for step in workflow["jobs"]["stop_legacy_verification"]["steps"]
        if "run" in step
    )
    az = tmp_path / "az"
    az.write_text(f"#!{sys.executable}\n{_AZ_STUB}")
    az.chmod(0o700)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o700)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "AZURE_ENV_NAME": "dev",
            "FUNCTION_ID": _FUNCTION_ID if present else "",
            "STATES": json.dumps(states),
            "FAIL": failure,
            "CALLS": str(calls),
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    assert message in result.stdout + result.stderr
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    if not present or failure == "lookup":
        assert len(commands) == 1
    if failure == "stop":
        assert len(commands) == 2
