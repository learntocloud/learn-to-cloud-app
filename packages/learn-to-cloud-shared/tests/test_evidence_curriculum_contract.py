"""Keep the published submission contract aligned with grading evidence."""

import pytest

from learn_to_cloud_shared.content_catalog import load_curriculum_catalog
from learn_to_cloud_shared.verification.tasks import VerificationTask
from learn_to_cloud_shared.verification.tasks.phase3 import (
    JOURNAL_API_FINAL_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
)
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
            JOURNAL_API_FINAL_RUBRIC_TASK,
            "build-the-app",
            {
                "api/main.py",
                "api/routers/journal_router.py",
                "api/models/entry.py",
                "api/services/entry_service.py",
                "api/services/llm_service.py",
                ".devcontainer/devcontainer.json",
                ".github/workflows/ci.yml",
                "pyproject.toml",
            },
            {
                "api/config.py",
                "api/repositories/interface_repository.py",
                "api/repositories/postgres_repository.py",
            },
        ),
        (
            DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
            "capstone",
            {"Dockerfile", "k8s/deployment.yaml", "k8s/service.yaml"},
            {".dockerignore", "k8s/secrets.yaml.example"},
        ),
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


def test_published_source_rules_and_boundaries() -> None:
    catalog = load_curriculum_catalog()
    task = DEVOPS_IMPLEMENTATION_RUBRIC_TASK
    requirement = catalog.requirements_by_slug["devops-implementation"]
    topic = catalog.topics_by_phase_and_slug[("phase5", "capstone")]
    for text in (requirement.description, topic.model_dump_json()):
        for rule in (
            "`.github/workflows/`",
            "`.yml`",
            "`.yaml`",
            "`infra/`",
            "`.tf`",
            "`.tf.json`",
            "`k8s/`",
            "`.terraform/`",
        ):
            assert rule in text
        assert "directly" in text
        assert "nested" in text
        assert "outside" in text
        assert "not" in text
    assert task.evidence.max_files == 24
    assert task.evidence.max_file_size_bytes == 50 * 1024
    assert task.evidence.max_total_bytes == 200 * 1024
    rules = {rule.root: rule for rule in task.evidence.directory_rules}
    assert set(rules) == {".github/workflows/", "infra/", "k8s/"}
    assert set(rules[".github/workflows/"].suffixes) == {".yml", ".yaml"}
    assert not rules[".github/workflows/"].recursive
    assert rules[".github/workflows/"].required
    assert set(rules["infra/"].suffixes) == {".tf", ".tf.json"}
    assert rules["infra/"].recursive
    assert rules["infra/"].required
    assert ".terraform" in rules["infra/"].excluded_directories
    assert set(rules["k8s/"].suffixes) == {".yml", ".yaml"}
    assert rules["k8s/"].recursive


def test_complete_text_and_ci_boundaries_are_published() -> None:
    catalog = load_curriculum_catalog()
    journal = catalog.requirements_by_slug["journal-api-implementation"]
    reflection = catalog.requirements_by_slug["career-reflection"]
    assert "CI evaluates tests" in journal.description
    assert "test files are not sent" in journal.description
    assert "complete submitted text" in reflection.description
    assert "no GitHub files are read" in reflection.description
    assert CAREER_REFLECTION_RUBRIC_TASK.evidence.required_files == [
        "career-reflection.md"
    ]
    assert all(
        requirement.submission_type != "deployment_architecture"
        for requirement in catalog.requirements_by_phase_slug["phase4"]
    )
