"""Tests for LLM verification grading helpers."""

from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import (
    TaskResult,
    ValidationResult,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.evidence import apply_evidence_cap
from learn_to_cloud_shared.verification.llm_grading import (
    LLMGradingDecisionPayload,
    _decision_to_grading_result,
    apply_llm_grading_decisions,
    llm_grading_content_filtered_result,
    llm_grading_unavailable_result,
)
from learn_to_cloud_shared.verification.tasks import (
    PHASE3_LLM_TASKS,
    PHASE5_LLM_TASKS,
    PHASE6_LLM_TASKS,
    PHASE7_LLM_TASKS,
    CriterionVerdict,
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
                    score=0.92,
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
                    score=0.91,
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
                    score=0.5,
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
                    score=0.79,
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
                    score=0.82,
                    feedback="Genuine, specific reflection across all three answers.",
                    evidence_refs=["career-reflection.md"],
                ),
            )
        ],
    )

    assert updated.validation_result.is_valid is True
    assert updated.validation_result.task_results is not None
    assert updated.validation_result.task_results[-1].passed is True


def test_failure_with_incomplete_evidence_is_marked_not_learner_fault() -> None:
    """A truncated file means the grader judged content we cut, not the learner."""
    task = PHASE5_LLM_TASKS[0]
    bundle = apply_evidence_cap(task, [("Dockerfile", "x" * (60 * 1024))])
    assert not bundle.is_sufficient

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.2,
            feedback="The Dockerfile does not pin a base image version.",
            next_steps="Pin the base image.",
            failure_reason="missing_pinned_base_image",
        ),
        bundle,
    )

    assert result.failure_reason == "insufficient_evidence"
    assert "Dockerfile" in result.feedback
    assert "could not read all of your work" in result.feedback.lower()


def test_pass_with_incomplete_evidence_is_left_alone() -> None:
    """Incomplete evidence that still cleared the rubric needs no caveat."""
    task = PHASE5_LLM_TASKS[0]
    bundle = apply_evidence_cap(task, [("Dockerfile", "x" * (60 * 1024))])

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.95,
            feedback="Solid pipeline.",
        ),
        bundle,
    )

    assert result.passed
    assert result.failure_reason is None
    assert result.feedback == "Solid pipeline."


def test_failure_with_complete_evidence_keeps_its_reason() -> None:
    task = PHASE5_LLM_TASKS[0]
    bundle = apply_evidence_cap(task, [("Dockerfile", "FROM python:3.13")])
    assert bundle.is_sufficient

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.2,
            feedback="No CI workflow found.",
            failure_reason="missing_ci_workflow",
        ),
        bundle,
    )

    assert result.failure_reason == "missing_ci_workflow"
    assert result.feedback == "No CI workflow found."


@pytest.mark.parametrize("offset", [-0.5, -0.01, 0.0, 0.2])
def test_score_alone_decides_the_outcome(offset: float) -> None:
    """The threshold lives in code, so the model cannot vote against its score."""
    task = PHASE3_LLM_TASKS[0]
    threshold = task.grader.passing_score
    score = min(max(threshold + offset, 0.0), 1.0)

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(score=score, feedback="Reviewed."),
    )

    assert result.passed is (score >= threshold)
    assert result.score == score


def test_a_model_supplied_passed_field_is_ignored() -> None:
    """Old-shape payloads must not resurrect a second source of truth."""
    task = PHASE3_LLM_TASKS[0]

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision.model_validate(
            {"passed": True, "score": 0.1, "feedback": "Reviewed."}
        ),
    )

    assert result.passed is False


def test_low_score_without_a_reason_gets_a_stable_fallback() -> None:
    result = _decision_to_grading_result(
        PHASE3_LLM_TASKS[0],
        LLMGradingDecision(score=0.1, feedback="Reviewed."),
    )

    assert result.failure_reason == "score_below_passing_threshold"


def test_failing_feedback_names_the_unmet_criteria() -> None:
    task = PHASE7_LLM_TASKS[0]

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.2,
            feedback="The reflection is too generic.",
            next_steps="Rewrite with specifics.",
            failure_reason="generic_answers",
            criteria=[
                CriterionVerdict(
                    index=0, met=True, justification="All three answered."
                ),
                CriterionVerdict(
                    index=1, met=False, justification="No personal detail."
                ),
                CriterionVerdict(index=2, met=False, justification="No outcome given."),
            ],
        ),
    )

    assert task.criteria[1] in result.next_steps
    assert task.criteria[2] in result.next_steps
    assert task.criteria[0] not in result.next_steps
    assert "Rewrite with specifics." in result.next_steps


def test_passing_result_does_not_list_criteria() -> None:
    task = PHASE7_LLM_TASKS[0]

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.95,
            feedback="Specific and personal throughout.",
            criteria=[CriterionVerdict(index=0, met=True)],
        ),
    )

    assert result.passed
    assert "Criteria not yet met" not in result.next_steps


def test_out_of_range_criterion_index_is_ignored() -> None:
    """A malformed verdict must not fail an attempt over prompt formatting."""
    task = PHASE7_LLM_TASKS[0]

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.2,
            feedback="Too generic.",
            next_steps="Add specifics.",
            criteria=[CriterionVerdict(index=99, met=False)],
        ),
    )

    assert result.next_steps == "Add specifics."


def test_criteria_verdicts_are_carried_onto_the_result() -> None:
    verdicts = [CriterionVerdict(index=0, met=False, justification="Missing.")]

    result = _decision_to_grading_result(
        PHASE7_LLM_TASKS[0],
        LLMGradingDecision(score=0.3, feedback="Reviewed.", criteria=verdicts),
    )

    assert result.criteria == verdicts


def test_criteria_do_not_override_the_score() -> None:
    """Verdicts are diagnostic; the score still decides the outcome."""
    task = PHASE7_LLM_TASKS[0]

    result = _decision_to_grading_result(
        task,
        LLMGradingDecision(
            score=0.95,
            feedback="Reviewed.",
            criteria=[CriterionVerdict(index=i, met=False) for i in range(3)],
        ),
    )

    assert result.passed
