"""Tests for LLM verification grading helpers."""

from uuid import uuid4

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    TaskResult,
    ValidationResult,
)
from learn_to_cloud_shared.verification.llm_grading import (
    LLMGradingDecisionPayload,
    apply_llm_grading_decisions,
    collect_llm_grading_requests,
    llm_grading_unavailable_result,
)
from learn_to_cloud_shared.verification.tasks import (
    PHASE3_LLM_TASKS,
    PHASE6_LLM_TASKS,
    LLMGradingDecision,
)
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationRunResult,
)


def _run_result(is_valid: bool = True) -> VerificationRunResult:
    requirement = HandsOnRequirement(
        id="security-scanning",
        submission_type=SubmissionType.SECURITY_SCANNING,
        name="Security scanning",
        description="Enable security scanning",
        required_repo="learntocloud/journal",
    )
    return VerificationRunResult(
        job=PreparedVerificationJob(
            id=uuid4(),
            user_id=1,
            github_username="learner",
            requirement=requirement,
            phase_id=6,
            submitted_value="https://github.com/learner/journal",
        ),
        validation_result=ValidationResult(
            is_valid=is_valid,
            message="Security scanning verified.",
            task_results=[
                TaskResult(
                    task_name="Dependabot Configuration",
                    passed=True,
                    feedback="Found valid Dependabot config.",
                )
            ],
        ),
    )


def _phase3_run_result(is_valid: bool = True) -> VerificationRunResult:
    requirement = HandsOnRequirement(
        id="journal-api-implementation",
        submission_type=SubmissionType.CI_STATUS,
        name="Verify Journal API Implementation",
        description="Verify that CI tests pass on the fork's main branch.",
        required_repo="learntocloud/journal-starter",
    )
    return VerificationRunResult(
        job=PreparedVerificationJob(
            id=uuid4(),
            user_id=1,
            github_username="learner",
            requirement=requirement,
            phase_id=3,
            submitted_value="https://github.com/learner/journal-starter",
        ),
        validation_result=ValidationResult(
            is_valid=is_valid,
            message="CI tests are passing on main.",
        ),
    )


@pytest.mark.unit
def test_apply_llm_grading_decisions_appends_feedback_when_passed():
    run_result = _run_result()

    updated = apply_llm_grading_decisions(
        run_result,
        [
            LLMGradingDecisionPayload(
                task=PHASE6_LLM_TASKS[0],
                decision=LLMGradingDecision(
                    passed=True,
                    score=0.92,
                    confidence=0.88,
                    feedback="The evidence satisfies the security scanning rubric.",
                    evidence_refs=[".github/dependabot.yml"],
                ),
            )
        ],
    )

    assert updated.validation_result.is_valid is True
    assert updated.validation_result.task_results is not None
    assert len(updated.validation_result.task_results) == 2
    assert updated.validation_result.task_results[-1].passed is True


@pytest.mark.unit
def test_apply_phase3_llm_decision_appends_feedback_when_passed():
    run_result = _phase3_run_result()

    updated = apply_llm_grading_decisions(
        run_result,
        [
            LLMGradingDecisionPayload(
                task=PHASE3_LLM_TASKS[0],
                decision=LLMGradingDecision(
                    passed=True,
                    score=0.91,
                    confidence=0.86,
                    feedback="The final Journal API implementation is maintainable.",
                    evidence_refs=["api/routers/journal_router.py"],
                ),
            )
        ],
    )

    assert updated.validation_result.is_valid is True
    assert updated.validation_result.task_results is not None
    assert updated.validation_result.task_results[-1].task_name == (
        "Journal API Final Rubric Review"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_collect_phase3_llm_requests_skips_when_ci_failed():
    requests = await collect_llm_grading_requests(_phase3_run_result(is_valid=False))

    assert requests == []


@pytest.mark.unit
def test_apply_llm_grading_decisions_fails_when_score_is_below_threshold():
    run_result = _run_result()

    updated = apply_llm_grading_decisions(
        run_result,
        [
            LLMGradingDecisionPayload(
                task=PHASE6_LLM_TASKS[0],
                decision=LLMGradingDecision(
                    passed=True,
                    score=0.5,
                    confidence=0.8,
                    feedback="The evidence is incomplete.",
                    next_steps="Add a Dependabot updates entry.",
                    evidence_refs=[".github/dependabot.yml"],
                ),
            )
        ],
    )

    assert updated.validation_result.is_valid is False
    assert updated.validation_result.message == (
        "LLM rubric review failed. Review the task feedback and try again."
    )
    assert updated.validation_result.task_results is not None
    assert updated.validation_result.task_results[-1].next_steps == (
        "Add a Dependabot updates entry."
    )


@pytest.mark.unit
def test_llm_grading_unavailable_result_marks_server_error():
    updated = llm_grading_unavailable_result(_run_result(), "structured output missing")

    assert updated.validation_result.is_valid is False
    assert updated.validation_result.verification_completed is False
    assert updated.validation_result.message == (
        "LLM verification grading failed: structured output missing"
    )
