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
    PHASE6_TASKS,
)
from learn_to_cloud_shared.verification.tasks.base import (
    FilePresenceGraderConfig,
    IndicatorGraderConfig,
    LLMRubricGraderConfig,
    require_file_presence_grader,
    require_indicator_grader,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification.tasks.phase3 import PHASE3_FINAL_REQUIREMENT_ID
from learn_to_cloud_shared.verification.tasks.phase5 import PHASE5_REQUIREMENT_ID
from learn_to_cloud_shared.verification.tasks.phase6 import PHASE6_REQUIREMENT_ID


@pytest.mark.unit
def test_phase_task_ids_are_stable_and_unique():
    """Task identifiers are stable API/telemetry keys."""
    tasks = [*PHASE5_TASKS, *PHASE6_TASKS]
    ids = [task.id for task in tasks]

    assert ids == [
        "dockerfile",
        "cicd-pipeline",
        "terraform-iac",
        "kubernetes-manifests",
        "dependabot",
        "codeql",
    ]
    assert len(ids) == len(set(ids))


@pytest.mark.unit
def test_phase5_tasks_use_indicator_graders():
    for task in PHASE5_TASKS:
        assert task.phase_id == 5
        assert task.requirement_id == PHASE5_REQUIREMENT_ID
        assert task.evidence.source == "repo_files"
        assert task.evidence.path_patterns
        assert task.evidence.required_files
        assert isinstance(require_indicator_grader(task), IndicatorGraderConfig)


@pytest.mark.unit
def test_phase6_tasks_use_file_presence_graders():
    for task in PHASE6_TASKS:
        assert task.phase_id == 6
        assert task.requirement_id == PHASE6_REQUIREMENT_ID
        assert task.evidence.source == "repo_files"
        assert task.evidence.path_patterns
        assert isinstance(require_file_presence_grader(task), FilePresenceGraderConfig)


@pytest.mark.unit
def test_phase3_llm_tasks_use_rubric_graders():
    assert [task.id for task in PHASE3_LLM_TASKS] == [
        "journal-api-implementation-rubric"
    ]
    task = PHASE3_LLM_TASKS[0]

    assert task.phase_id == 3
    assert task.requirement_id == PHASE3_FINAL_REQUIREMENT_ID
    assert task.evidence.source == "repo_files"
    assert isinstance(require_llm_rubric_grader(task), LLMRubricGraderConfig)


@pytest.mark.unit
def test_phase6_llm_tasks_use_rubric_graders():
    assert [task.id for task in PHASE6_LLM_TASKS] == ["security-scanning-rubric"]
    task = PHASE6_LLM_TASKS[0]

    assert task.phase_id == 6
    assert task.requirement_id == PHASE6_REQUIREMENT_ID
    assert task.evidence.source == "repo_files"
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
    task = PHASE6_TASKS[0]

    result = grade_file_presence_task(
        task,
        [".github/dependabot.yml"],
        {".github/dependabot.yml": "version: 2\nupdates: []\n"},
    )

    assert result.task_id == "dependabot"
    assert result.grader_kind == "file_presence"
    assert result.passed is True
