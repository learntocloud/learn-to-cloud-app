"""First-party tests stay out of deployable application payloads."""

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]


def test_docker_excludes_first_party_test_trees():
    patterns = (_ROOT / ".dockerignore").read_text().splitlines()

    for member in (
        "api",
        "packages/learn-to-cloud-shared",
    ):
        assert f"/{member}/tests/" in patterns


def test_docker_resolves_the_development_workspace_manifest():
    dockerfile = (_ROOT / "api/Dockerfile").read_text()
    manifest = "packages/learn-to-cloud-shared-test-support/pyproject.toml"

    assert f"COPY {manifest} {manifest}" in dockerfile
    assert dockerfile.index(f"COPY {manifest}") < dockerfile.index("RUN uv sync")


def test_deployment_does_not_package_a_functions_host():
    workflow = yaml.safe_load((_ROOT / ".github/workflows/app-deploy.yml").read_text())
    deploys = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("Azure/functions-action@")
    ]
    assert not deploys


@pytest.mark.parametrize(
    ("workflow_name", "category"), [("ci.yml", "code"), ("app-deploy.yml", "app")]
)
def test_packaging_changes_trigger_quality_and_deployment(workflow_name, category):
    workflow = yaml.load(
        (_ROOT / ".github/workflows" / workflow_name).read_text(),
        Loader=yaml.BaseLoader,
    )
    filters = next(
        step["with"]["filters"]
        for step in workflow["jobs"]["changes"]["steps"]
        if step.get("id") == "filter"
    )
    paths = yaml.safe_load(filters)[category]
    assert ".dockerignore" in paths
    assert ".github/workflows/app-deploy.yml" in paths
    if workflow_name == "app-deploy.yml":
        assert ".dockerignore" in workflow["on"]["push"]["paths"]
