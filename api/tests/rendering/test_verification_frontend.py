"""Browser-controller contracts exercised with the existing Node runtime."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.unit
@pytest.mark.parametrize("reduced_motion", [False, True])
def test_verification_transitions(reduced_motion: bool) -> None:
    script = Path(__file__).parents[2] / "src/learn_to_cloud/static/js/verification.js"
    harness = Path(__file__).with_name("verification_frontend.cjs")
    subprocess.run(
        ["node", str(harness), str(script), str(reduced_motion).lower()],
        check=True,
        capture_output=True,
        text=True,
    )
