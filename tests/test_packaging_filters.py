"""First-party tests stay out of deployable application payloads."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_docker_excludes_first_party_tests_and_authored_curriculum():
    patterns = (_ROOT / ".dockerignore").read_text().splitlines()
    content = "/src/learn_to_cloud/content"

    assert "/tests/" in patterns
    assert f"{content}/phases/" in patterns
    assert f"{content}/schemas/" in patterns
    assert f"{content}/curriculum.meta.yaml" in patterns
