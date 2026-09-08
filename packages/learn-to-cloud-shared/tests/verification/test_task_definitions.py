"""Contract tests for the active verification task definitions."""

import pytest

from learn_to_cloud_shared.verification.tasks import (
    CAREER_REFLECTION_RUBRIC_TASK,
    SECURITY_SCANNING_RUBRIC_TASK,
    LLMRubricGraderConfig,
)


@pytest.mark.unit
def test_security_scanning_task_uses_repository_rubric():
    task = SECURITY_SCANNING_RUBRIC_TASK
    assert task.id == "security-scanning-rubric"
    assert task.phase_id == 6
    assert task.requirement_slug == "security-scanning"
    assert task.evidence.source == "repo_files"
    assert task.evidence.required_files == [".github/workflows/codeql.yml"]
    assert isinstance(task.grader, LLMRubricGraderConfig)


@pytest.mark.unit
def test_career_reflection_task_uses_submitted_text():
    task = CAREER_REFLECTION_RUBRIC_TASK
    assert task.id == "career-reflection-rubric"
    assert task.phase_id == 7
    assert task.requirement_slug == "career-reflection"
    assert task.evidence.source == "submitted_text"
    assert isinstance(task.grader, LLMRubricGraderConfig)
