"""Keep the published submission contract aligned with grading evidence."""

import pytest

from learn_to_cloud_shared.content_catalog import load_curriculum_catalog
from learn_to_cloud_shared.verification.ci_status import CAPSTONE_WORKFLOW_FILE
from learn_to_cloud_shared.verification.devops_analysis import (
    DEVOPS_REQUIRED_JOBS,
    DEVOPS_WORKFLOW_FILE,
)
from learn_to_cloud_shared.verification.tasks import VerificationTask
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("task", "topic_slug", "required", "optional"),
    [
        (
            SECURITY_SCANNING_RUBRIC_TASK,
            "capstone",
            {".github/workflows/codeql.yml"},
            {".github/dependabot.yml"},
        ),
    ],
)
def test_named_evidence_is_published(
    task: VerificationTask,
    topic_slug: str,
    required: set[str],
    optional: set[str],
) -> None:
    catalog = load_curriculum_catalog()
    assert task.requirement_slug is not None
    requirement = catalog.requirements_by_slug[task.requirement_slug]
    topic = catalog.topics_by_phase_and_slug[(f"phase{task.phase_id}", topic_slug)]

    assert set(task.evidence.required_files) == required
    assert set(task.evidence.optional_files) == optional
    for path in required | optional:
        assert f"`{path}`" in requirement.description
        assert f"`{path}`" in topic.model_dump_json()


def test_devops_run_and_job_contract_is_published() -> None:
    catalog = load_curriculum_catalog()
    requirement = catalog.requirements_by_slug["devops-implementation"]
    topic = catalog.topics_by_phase_and_slug[("phase5", "capstone")]
    assert str(requirement.uuid) == "623a87ae-156f-42da-a83c-09241d523e00"
    assert requirement.submission_type == "devops_analysis"
    for text in (requirement.description, topic.model_dump_json()):
        assert f"`.github/workflows/{DEVOPS_WORKFLOW_FILE}`" in text
        assert "latest run" in text
        assert "current `main` commit" in text
        for job in DEVOPS_REQUIRED_JOBS:
            assert f"`{job}`" in text
        assert "Re-run all jobs" in text
        assert "run and job results" in text
        assert "public GHCR" not in text
        assert "Required evidence" not in text


def test_capstone_workflow_and_local_responsibilities_are_published() -> None:
    catalog = load_curriculum_catalog()
    journal = catalog.requirements_by_slug["journal-api-implementation"]
    topic = catalog.topics_by_phase_and_slug[("phase3", "build-the-app")]
    assert str(journal.uuid) == "d6201101-8873-447a-957a-0e5773627618"
    assert journal.submission_type == "journal_api_verifier"
    assert f"`{CAPSTONE_WORKFLOW_FILE}`" in journal.description
    assert "latest commit" in journal.description
    assert "`main` branch" in journal.description
    text = topic.model_dump_json()
    assert f".github/workflows/{CAPSTONE_WORKFLOW_FILE}" in text
    assert "current `main` commit" in text
    assert "Rerun" in text
    assert "Ordinary CI" in text
    assert "local responsibilities" in text
    assert "offline workflow does not verify them" in text
    for published in (journal.description, text):
        assert "canonical" not in published
        assert "evidence limit" not in published
    genai = catalog.topics_by_phase_and_slug[("phase3", "genai-apis")]
    assert genai.learning_steps[-1].url == (
        "https://github.com/learntocloud/journal-starter/blob/main/docs/08-ai-setup.md"
    )


def test_complete_text_boundaries_are_published() -> None:
    catalog = load_curriculum_catalog()
    reflection = catalog.requirements_by_slug["career-reflection"]
    assert "complete submitted text" in reflection.description
    assert "no GitHub files are read" in reflection.description
    assert CAREER_REFLECTION_RUBRIC_TASK.evidence.required_files == [
        "career-reflection.md"
    ]
    assert all(
        requirement.submission_type != "deployment_architecture"
        for requirement in catalog.requirements_by_phase_slug["phase4"]
    )
