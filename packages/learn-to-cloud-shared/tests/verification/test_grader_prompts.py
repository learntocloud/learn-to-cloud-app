"""Tests for the versioned per-phase grader prompt registry."""

from __future__ import annotations

from hashlib import sha256

import pytest

from learn_to_cloud_shared.verification.grader_prompts import (
    GRADER_PROMPTS,
    GraderPrompt,
    prompt_for_task,
)
from learn_to_cloud_shared.verification.tasks import (
    CAREER_REFLECTION_RUBRIC_TASK,
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
    JOURNAL_API_FINAL_RUBRIC_TASK,
    SECURITY_SCANNING_RUBRIC_TASK,
    VerificationTask,
)

ALL_RUBRIC_TASKS = [
    JOURNAL_API_FINAL_RUBRIC_TASK,
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
    SECURITY_SCANNING_RUBRIC_TASK,
    CAREER_REFLECTION_RUBRIC_TASK,
]


@pytest.mark.parametrize("task", ALL_RUBRIC_TASKS, ids=lambda task: task.id)
def test_every_rubric_task_resolves_a_prompt(task: VerificationTask) -> None:
    prompt = prompt_for_task(task)
    assert prompt.id == task.grader.prompt_id
    assert prompt.instructions.strip()


def test_each_phase_gets_a_distinct_prompt() -> None:
    resolved = {prompt_for_task(task).id for task in ALL_RUBRIC_TASKS}
    assert len(resolved) == len(ALL_RUBRIC_TASKS)


def test_registry_keys_match_prompt_ids() -> None:
    assert all(key == prompt.id for key, prompt in GRADER_PROMPTS.items())


def test_checksum_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="checksum"):
        GraderPrompt(
            id="test",
            version="2026-01-01",
            instructions="some instructions",
            checksum="0" * 16,
        )


def test_checksum_matches_instruction_text() -> None:
    for prompt in GRADER_PROMPTS.values():
        expected = sha256(prompt.instructions.encode("utf-8")).hexdigest()[:16]
        assert prompt.checksum == expected


def test_unknown_prompt_id_raises() -> None:
    task = CAREER_REFLECTION_RUBRIC_TASK.model_copy(
        update={
            "grader": CAREER_REFLECTION_RUBRIC_TASK.grader.model_copy(
                update={"prompt_id": "does-not-exist"}
            )
        }
    )
    with pytest.raises(LookupError, match="does-not-exist"):
        prompt_for_task(task)
