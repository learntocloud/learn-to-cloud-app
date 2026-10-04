"""Keep the published submission contract aligned with grading evidence."""

import pytest

from learn_to_cloud.curriculum.catalog import load_curriculum_catalog
from learn_to_cloud.verification.ci_status import CAPSTONE_WORKFLOW_FILE
from learn_to_cloud.verification.devops_verification import (
    DEVOPS_ENVIRONMENT,
    DEVOPS_REQUIRED_JOBS,
    DEVOPS_VERSION_PATH,
    DEVOPS_WORKFLOW_FILE,
)
from learn_to_cloud.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)

pytestmark = pytest.mark.unit


def _requirement(catalog, slug):
    return next(
        requirement
        for requirement in catalog.requirements_by_uuid.values()
        if requirement.slug == slug
    )


def _topic(catalog, phase_slug, topic_slug):
    return next(
        topic
        for topic in catalog.phases_by_slug[phase_slug].topics
        if topic.slug == topic_slug
    )


def test_devops_run_and_job_contract_is_published() -> None:
    catalog = load_curriculum_catalog()
    requirement = _requirement(catalog, "devops-implementation")
    topic = _topic(catalog, "phase5", "capstone")
    assert str(requirement.uuid) == "623a87ae-156f-42da-a83c-09241d523e00"
    assert requirement.submission_type == "devops_verification"
    for text in (requirement.description, topic.model_dump_json()):
        assert f"`.github/workflows/{DEVOPS_WORKFLOW_FILE}`" in text
        assert "latest run" in text
        assert "current `main` commit" in text
        for job in DEVOPS_REQUIRED_JOBS:
            assert f"`{job}`" in text
        assert "Re-run all jobs" in text
        assert "run and job results" in text
        assert f"`{DEVOPS_ENVIRONMENT}`" in text
        assert f"`GET {DEVOPS_VERSION_PATH}`" in text
        assert "HTTPS" in text
        assert "public GHCR" not in text
        assert "Required evidence" not in text


def test_capstone_workflow_and_local_responsibilities_are_published() -> None:
    catalog = load_curriculum_catalog()
    journal = _requirement(catalog, "journal-api-implementation")
    topic = _topic(catalog, "phase3", "build-the-app")
    assert str(journal.uuid) == "d6201101-8873-447a-957a-0e5773627618"
    assert journal.submission_type == "journal_api_verifier"
    assert f"`{CAPSTONE_WORKFLOW_FILE}`" in journal.description
    assert "latest commit" in journal.description
    assert "`main` branch" in journal.description
    text = topic.model_dump_json()
    assert f".github/workflows/{CAPSTONE_WORKFLOW_FILE}" in text
    assert "current `main` commit" in text
    assert "Rerun" in text
    assert "live AI verification" in text
    assert "cloud CLI check" in text
    assert "green CI badge is not the capstone check" in text
    assert "never commit `.env` files or provider credentials" in text
    for published in (journal.description, text):
        assert "canonical" not in published
        assert "evidence limit" not in published
    genai = _topic(catalog, "phase3", "genai-apis")
    assert genai.learning_steps[-1].url == (
        "https://github.com/learntocloud/journal-starter/blob/main/docs/08-ai-setup.md"
    )


def test_complete_text_boundaries_are_published() -> None:
    catalog = load_curriculum_catalog()
    reflection = _requirement(catalog, "career-reflection")
    assert "complete submitted text" in reflection.description
    assert "no GitHub files are read" in reflection.description
    assert CAREER_REFLECTION_RUBRIC_TASK.evidence.required_files == [
        "career-reflection.md"
    ]
    assert all(
        requirement.submission_type != "deployment_architecture"
        for requirement in catalog.requirements_by_phase_slug["phase4"]
    )
