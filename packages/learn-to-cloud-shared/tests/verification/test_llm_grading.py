"""Tests for LLM verification grading helpers."""

from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import (
    TaskResult,
    ValidationResult,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.llm_grading import (
    LLMGradingDecisionPayload,
    apply_llm_grading_decisions,
    llm_grading_content_filtered_result,
    llm_grading_unavailable_result,
)
from learn_to_cloud_shared.verification.tasks import (
    PHASE3_LLM_TASKS,
    PHASE5_LLM_TASKS,
    PHASE6_LLM_TASKS,
    PHASE7_LLM_TASKS,
    LLMGradingDecision,
)
from learn_to_cloud_shared.verification_workflow import (
    PreparedVerificationAttempt,
    VerificationRunResult,
)


def _run_result(is_valid: bool = True) -> VerificationRunResult:
    from learn_to_cloud_shared.testing.requirement_factories import (
        security_scanning_requirement,
    )

    requirement = security_scanning_requirement(
        slug="security-scanning",
        name="Security scanning",
        description="Enable security scanning",
        required_repo="learntocloud/journal",
    )
    return VerificationRunResult(
        attempt=PreparedVerificationAttempt(
            id=uuid4(),
            user_id=1,
            github_username="learner",
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(
                requirement, "https://github.com/learner/journal"
            ),
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
    from learn_to_cloud_shared.testing.requirement_factories import (
        journal_api_verifier_requirement,
    )

    requirement = journal_api_verifier_requirement(
        slug="journal-api-implementation",
        name="Verify Journal API Implementation",
        description="Verify that CI tests pass on the fork's main branch.",
        required_repo="learntocloud/journal-starter",
    )
    return VerificationRunResult(
        attempt=PreparedVerificationAttempt(
            id=uuid4(),
            user_id=1,
            github_username="learner",
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(
                requirement, "https://github.com/learner/journal-starter"
            ),
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
def test_phase5_holistic_review_enforces_strict_threshold():
    updated = apply_llm_grading_decisions(
        _run_result(),
        [
            LLMGradingDecisionPayload(
                task=PHASE5_LLM_TASKS[0],
                decision=LLMGradingDecision(
                    passed=True,
                    score=0.79,
                    confidence=0.9,
                    feedback="Most areas are sound, but the manifests conflict.",
                    next_steps="Align the image and port configuration.",
                    evidence_refs=["Dockerfile", "k8s/deployment.yaml"],
                ),
            )
        ],
    )

    assert updated.validation_result.is_valid is False
    assert updated.validation_result.task_results is not None
    result = updated.validation_result.task_results[-1]
    assert result.task_name == "DevOps Implementation Review"
    assert result.passed is False


@pytest.mark.unit
def test_llm_grading_unavailable_result_marks_server_error():
    updated = llm_grading_unavailable_result(_run_result())

    assert updated.validation_result.is_valid is False
    assert updated.validation_result.verification_completed is False
    assert updated.validation_result.message == (
        "Automated grading is temporarily unavailable. This is a "
        "problem on our end, not yours. Please report it so we can "
        "fix it."
    )


def test_llm_grading_content_filtered_result_asks_learner_to_rephrase():
    updated = llm_grading_content_filtered_result(_run_result())

    assert updated.validation_result.is_valid is False
    assert updated.validation_result.verification_completed is False
    assert "content safety filter" in updated.validation_result.message
    assert "rewrite your answers" in updated.validation_result.message


def _phase7_run_result(
    is_valid: bool = True,
    submitted_text: str = "## Question 0?\n\nMy detailed reflection answer.",
) -> VerificationRunResult:
    from learn_to_cloud_shared.testing.requirement_factories import (
        career_reflection_requirement,
    )

    requirement = career_reflection_requirement(
        slug="career-reflection",
        name="Reflect on Your Job-Search Readiness",
        description="Answer three reflection questions.",
    )
    return VerificationRunResult(
        attempt=PreparedVerificationAttempt(
            id=uuid4(),
            user_id=1,
            github_username="learner",
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(requirement, submitted_text),
        ),
        validation_result=ValidationResult(
            is_valid=is_valid,
            message="Reflection received. Reviewing your answers.",
        ),
    )


@pytest.mark.unit
def test_apply_phase7_llm_decision_appends_feedback_when_passed():
    updated = apply_llm_grading_decisions(
        _phase7_run_result(),
        [
            LLMGradingDecisionPayload(
                task=PHASE7_LLM_TASKS[0],
                decision=LLMGradingDecision(
                    passed=True,
                    score=0.82,
                    confidence=0.8,
                    feedback="Genuine, specific reflection across all three answers.",
                    evidence_refs=["career-reflection.md"],
                ),
            )
        ],
    )

    assert updated.validation_result.is_valid is True
    assert updated.validation_result.task_results is not None
    assert updated.validation_result.task_results[-1].passed is True
