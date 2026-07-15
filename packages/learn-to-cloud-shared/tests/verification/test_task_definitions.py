"""Contract tests for shared verification task definitions."""

import pytest

from learn_to_cloud_shared.verification.graders import grade_file_presence_task
from learn_to_cloud_shared.verification.tasks import (
    PHASE3_LLM_TASKS,
    PHASE6_LLM_TASKS,
    PHASE7_LLM_TASKS,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    FilePresenceGraderConfig,
    LLMRubricGraderConfig,
    VerificationTask,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification.tasks.phase3 import (
    PHASE3_FINAL_REQUIREMENT_SLUG,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    PHASE5_EVIDENCE_PATH_PATTERNS,
    PHASE5_REQUIRED_PATHS,
)
from learn_to_cloud_shared.verification.tasks.phase6 import PHASE6_REQUIREMENT_SLUG
from learn_to_cloud_shared.verification.tasks.phase7 import PHASE7_REQUIREMENT_SLUG


@pytest.mark.unit
def test_phase5_repository_contract_is_stable():
    assert PHASE5_REQUIRED_PATHS == (
        "Dockerfile",
        ".github/workflows/",
        "infra/",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
    )
    assert PHASE5_EVIDENCE_PATH_PATTERNS[:5] == (
        "Dockerfile",
        ".dockerignore",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
        "k8s/secrets.yaml.example",
    )


@pytest.mark.unit
def test_phase3_llm_tasks_use_rubric_graders():
    assert [task.id for task in PHASE3_LLM_TASKS] == [
        "journal-api-implementation-rubric"
    ]
    task = PHASE3_LLM_TASKS[0]

    assert task.phase_id == 3
    assert task.requirement_slug == PHASE3_FINAL_REQUIREMENT_SLUG
    assert task.evidence.source == "repo_files"
    assert isinstance(require_llm_rubric_grader(task), LLMRubricGraderConfig)


@pytest.mark.unit
def test_phase6_llm_tasks_use_rubric_graders():
    assert [task.id for task in PHASE6_LLM_TASKS] == ["security-scanning-rubric"]
    task = PHASE6_LLM_TASKS[0]

    assert task.phase_id == 6
    assert task.requirement_slug == PHASE6_REQUIREMENT_SLUG
    assert task.evidence.source == "repo_files"
    assert ".github/workflows/codeql.yml" in task.evidence.path_patterns
    assert isinstance(require_llm_rubric_grader(task), LLMRubricGraderConfig)


@pytest.mark.unit
def test_phase7_llm_tasks_use_rubric_graders_over_submitted_text():
    assert [task.id for task in PHASE7_LLM_TASKS] == ["career-reflection-rubric"]
    task = PHASE7_LLM_TASKS[0]

    assert task.phase_id == 7
    assert task.requirement_slug == PHASE7_REQUIREMENT_SLUG
    assert task.evidence.source == "submitted_text"
    assert isinstance(require_llm_rubric_grader(task), LLMRubricGraderConfig)


@pytest.mark.unit
def test_file_presence_grader_returns_normalized_result():
    task = VerificationTask(
        id="dependabot",
        phase_id=6,
        requirement_slug=PHASE6_REQUIREMENT_SLUG,
        name="Dependabot Configuration",
        criteria=["MUST include a .github/dependabot.yml file"],
        evidence=EvidencePolicy(
            source="repo_files",
            path_patterns=[".github/dependabot.yml"],
            max_files=1,
        ),
        grader=FilePresenceGraderConfig(
            required_any=[".github/dependabot.yml"],
            content_indicators=["version", "updates"],
        ),
    )

    result = grade_file_presence_task(
        task,
        [".github/dependabot.yml"],
        {".github/dependabot.yml": "version: 2\nupdates: []\n"},
    )

    assert result.task_id == "dependabot"
    assert result.grader_kind == "file_presence"
    assert result.passed is True
