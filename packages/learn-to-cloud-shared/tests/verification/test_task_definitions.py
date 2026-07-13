"""Contract tests for shared verification task definitions."""

import pytest

from learn_to_cloud_shared.verification.graders import (
    grade_file_presence_task,
    grade_indicator_task,
)
from learn_to_cloud_shared.verification.tasks import (
    PHASE3_LLM_TASKS,
    PHASE5_TASKS,
    PHASE6_LLM_TASKS,
    PHASE7_LLM_TASKS,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    FilePresenceGraderConfig,
    IndicatorGraderConfig,
    LLMRubricGraderConfig,
    VerificationTask,
    require_indicator_grader,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification.tasks.phase3 import (
    PHASE3_FINAL_REQUIREMENT_SLUG,
)
from learn_to_cloud_shared.verification.tasks.phase5 import PHASE5_REQUIREMENT_SLUG
from learn_to_cloud_shared.verification.tasks.phase6 import PHASE6_REQUIREMENT_SLUG
from learn_to_cloud_shared.verification.tasks.phase7 import PHASE7_REQUIREMENT_SLUG


@pytest.mark.unit
def test_phase_task_ids_are_stable_and_unique():
    """Task identifiers are stable API/telemetry keys."""
    ids = [task.id for task in PHASE5_TASKS]

    assert ids == [
        "dockerfile",
        "cicd-pipeline",
        "terraform-iac",
        "kubernetes-manifests",
    ]
    assert len(ids) == len(set(ids))


@pytest.mark.unit
def test_phase5_tasks_use_indicator_graders():
    for task in PHASE5_TASKS:
        assert task.phase_id == 5
        assert task.requirement_slug == PHASE5_REQUIREMENT_SLUG
        assert task.evidence.source == "repo_files"
        assert task.evidence.path_patterns
        assert task.evidence.required_files
        assert isinstance(require_indicator_grader(task), IndicatorGraderConfig)


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
def test_indicator_grader_returns_normalized_result():
    task = PHASE5_TASKS[0]

    result = grade_indicator_task(
        task,
        [
            "FROM python:3.13\n"
            "COPY . .\n"
            "RUN uv sync\n"
            "ENV PYTHONPATH=/app\n"
            "EXPOSE 8000\n"
            "CMD uvicorn learn_to_cloud.main:app\n"
        ],
    )

    assert result.task_id == "dockerfile"
    assert result.grader_kind == "indicator"
    assert result.passed is True
    assert result.to_task_result().task_name == task.name


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
