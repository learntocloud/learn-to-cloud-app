"""Typed preparation, grading, and finalization run without attempt retries."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.submission_values import submitted_value_from_raw
from learn_to_cloud_shared.verification.evidence import (
    EVIDENCE_ERROR_CODES,
    EvidenceError,
    apply_evidence_cap,
)
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingRequest,
    build_text_rubric_message,
)
from learn_to_cloud_shared.verification.tasks import LLMGradingDecision, RubricCriterion
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification_workflow import (
    LLM_ERROR_TYPES,
    PreparedVerificationAttempt,
    VerificationRunResult,
)
from learn_to_cloud_shared_test_support.requirement_factories import (
    devops_analysis_requirement,
)

from learn_to_cloud.services import verification_runner as runner
from learn_to_cloud.services.verification_grader import (
    ContentFilteredError,
    LLMGradingError,
)


def _reflection_request(text: str = "Complete text 雲") -> LLMGradingRequest:
    task = CAREER_REFLECTION_RUBRIC_TASK
    bundle = apply_evidence_cap(task, [("career-reflection.md", text)])
    return LLMGradingRequest(
        task=task,
        message=build_text_rubric_message(
            requirement_slug="reflection",
            requirement_name="Reflection",
            deterministic_result=ValidationResult(is_valid=True, message="Complete"),
            task=task,
            evidence=bundle.model_dump(mode="json"),
        ),
        allowed_evidence_refs=["career-reflection.md"],
    )


def _decision(*, passed: bool = True, score: float = 1.0) -> LLMGradingDecision:
    return LLMGradingDecision.model_validate(
        {
            "passed": passed,
            "score": score,
            "confidence": 0.9,
            "feedback": "Personal, specific reflections.",
            "next_steps": "" if passed else "Give a concrete example.",
            "failure_reason": None if passed else "incomplete_reflection",
            "evidence_refs": ["career-reflection.md"],
            "criterion_results": [
                {
                    "criterion_id": criterion.id,
                    "status": "met" if passed else "not_met",
                    "explanation": "Specific personal evidence.",
                    "next_steps": "" if passed else "Give a concrete example.",
                    "evidence_refs": ["career-reflection.md"],
                }
                for criterion in CAREER_REFLECTION_RUBRIC_TASK.criteria
                if isinstance(criterion, RubricCriterion)
            ],
        }
    )


async def test_grading_rejects_missing_evidence_contract(execution):
    request = _reflection_request()
    prefix, body = request.message.split("\n\n", 1)
    payload = json.loads(body)
    del payload["task"]["evidence_contract"]
    execution.verify.return_value = replace(
        execution.result,
        grading_requests=[
            request.model_copy(update={"message": f"{prefix}\n\n{json.dumps(payload)}"})
        ],
    )

    finalized = await _execute(execution)

    execution.grade.assert_not_awaited()
    assert finalized.validation_result.error_code == "evidence.selection"
    assert not finalized.validation_result.verification_completed


@pytest.fixture
def execution(monkeypatch):
    requirement = devops_analysis_requirement(slug="devops")
    attempt = PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="alice",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(
            requirement, "https://github.com/alice/journal"
        ),
    )
    run_result = VerificationRunResult(
        attempt=attempt,
        validation_result=ValidationResult(is_valid=True, message="Complete"),
        grading_requests=[_reflection_request()],
    )
    calls = Mock()
    prepare = AsyncMock(return_value=attempt)
    verify = AsyncMock(return_value=run_result)
    grade = AsyncMock(return_value=_decision())
    finalize = AsyncMock()
    for name, mock in (
        ("prepare_verification_attempt", prepare),
        ("run_verification", verify),
        ("grade_evidence", grade),
        ("finalize_verification_attempt", finalize),
    ):
        monkeypatch.setattr(runner, name, mock)
        calls.attach_mock(mock, name)
    config = Mock(return_value=[])
    monkeypatch.setattr(runner, "missing_grading_config", config)
    return SimpleNamespace(
        attempt=attempt,
        result=run_result,
        prepare=prepare,
        verify=verify,
        grade=grade,
        finalize=finalize,
        config=config,
        calls=calls,
        session_maker=Mock(),
    )


async def _execute(execution) -> VerificationRunResult:
    result = await runner.execute_verification_attempt(
        execution.attempt.id, session_maker=execution.session_maker
    )
    assert result is None
    execution.prepare.assert_awaited_once_with(
        execution.attempt.id, session_maker=execution.session_maker
    )
    execution.verify.assert_awaited_once_with(execution.attempt)
    execution.finalize.assert_awaited_once()
    assert execution.finalize.call_args.kwargs == {
        "session_maker": execution.session_maker
    }
    return execution.finalize.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("requests", [None, []])
async def test_deterministic_result_finalizes_without_grading(execution, requests):
    execution.verify.return_value = replace(execution.result, grading_requests=requests)

    finalized = await _execute(execution)

    assert finalized is execution.verify.return_value
    execution.grade.assert_not_awaited()
    execution.config.assert_not_called()
    assert [call[0] for call in execution.calls.mock_calls] == [
        "prepare_verification_attempt",
        "run_verification",
        "finalize_verification_attempt",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("passed", "score", "expected"),
    [(True, 1.0, True), (True, 0.1, False), (False, 0, False)],
)
async def test_grading_preserves_rubric_feedback_and_threshold(
    execution, passed, score, expected
):
    execution.grade.return_value = _decision(passed=passed, score=score)

    finalized = await _execute(execution)

    assert finalized.validation_result.is_valid is expected
    tasks = finalized.validation_result.task_results
    assert tasks is not None
    assert len(tasks) == 1
    assert tasks[0].passed is expected
    assert tasks[0].feedback == "Personal, specific reflections."
    assert len(tasks[0].criterion_results) == len(
        CAREER_REFLECTION_RUBRIC_TASK.criteria
    )
    for criterion in tasks[0].criterion_results:
        assert criterion.evidence_refs == ["career-reflection.md"]
        assert criterion.label
        assert criterion.status == ("met" if passed else "not_met")
    assert finalized.grading_requests is None
    assert [call[0] for call in execution.calls.mock_calls] == [
        "prepare_verification_attempt",
        "run_verification",
        "grade_evidence",
        "finalize_verification_attempt",
    ]


@pytest.mark.asyncio
async def test_multiple_requests_are_graded_sequentially(execution):
    first, second = _reflection_request("first"), _reflection_request("second")
    execution.verify.return_value = replace(
        execution.result, grading_requests=[first, second]
    )
    finalized = await _execute(execution)
    assert [call.args[0] for call in execution.grade.await_args_list] == [
        first.message,
        second.message,
    ]
    tasks = finalized.validation_result.task_results
    assert tasks is not None
    assert len(tasks) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("valid", "completed"), [(False, False), (False, True), (True, False)]
)
async def test_failed_gate_never_grades_stale_requests(execution, valid, completed):
    execution.verify.return_value = replace(
        execution.result,
        validation_result=ValidationResult(
            is_valid=valid, verification_completed=completed, message="Gate failed"
        ),
    )
    assert await _execute(execution) is execution.verify.return_value
    execution.grade.assert_not_awaited()
    execution.config.assert_not_called()


@pytest.mark.asyncio
async def test_missing_config_finalizes_unavailable(execution, caplog):
    execution.config.return_value = ["FOUNDRY_PROJECT_ENDPOINT"]
    finalized = await _execute(execution)
    assert finalized.llm_error_type == "llm.configuration"
    assert finalized.validation_result.verification_completed is False
    execution.grade.assert_not_awaited()
    assert [r.message for r in caplog.records] == ["verification.llm_grading.failed"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type", sorted(LLM_ERROR_TYPES) + ["secret provider details"]
)
async def test_bounded_grading_failure_finalizes_once(execution, caplog, error_type):
    execution.grade.side_effect = LLMGradingError(error_type)
    finalized = await _execute(execution)
    expected = error_type if error_type in LLM_ERROR_TYPES else "llm.unknown"
    assert finalized.llm_error_type == expected
    assert finalized.validation_result.verification_completed is False
    execution.grade.assert_awaited_once()
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "verification.llm_grading.failed"
    assert record.__dict__["error.type"] == expected
    assert record.exc_info is None
    assert "secret provider details" not in caplog.text


@pytest.mark.asyncio
async def test_content_filter_finalizes_without_operational_error_event(
    execution, caplog
):
    execution.grade.side_effect = ContentFilteredError()
    finalized = await _execute(execution)
    assert finalized.validation_result.is_valid is False
    assert finalized.validation_result.verification_completed is True
    assert "content safety filter" in finalized.validation_result.message
    assert finalized.llm_error_type is None
    execution.grade.assert_awaited_once()
    assert caplog.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize("code", sorted(EVIDENCE_ERROR_CODES))
async def test_evidence_failure_keeps_code_and_drops_prompts(
    execution, monkeypatch, caplog, code
):
    monkeypatch.setattr(
        runner, "validate_grading_request", Mock(side_effect=EvidenceError(code))
    )
    finalized = await _execute(execution)
    assert finalized.validation_result.error_code == code
    assert finalized.validation_result.is_valid is False
    assert finalized.validation_result.verification_completed is (
        code == "evidence.required_missing"
    )
    assert finalized.validation_result.task_results is None
    assert finalized.llm_error_type is None
    assert finalized.grading_requests is None
    execution.grade.assert_not_awaited()
    assert caplog.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["truncated", "failed", "incomplete", "invalid"])
async def test_corrupt_evidence_is_checked_before_provider(execution, corruption):
    request = _reflection_request()
    prefix, raw = request.message.split("\n\n", 1)
    message = json.loads(raw)
    if corruption == "truncated":
        message["evidence"]["items"][0]["truncated"] = True
    elif corruption == "failed":
        message["deterministic_result"]["is_valid"] = False
    elif corruption == "incomplete":
        message["deterministic_result"]["verification_completed"] = False
    else:
        message = {}
    request = request.model_copy(
        update={"message": f"{prefix}\n\n{json.dumps(message)}"}
    )
    execution.verify.return_value = replace(
        execution.result, grading_requests=[request]
    )
    finalized = await _execute(execution)
    assert finalized.validation_result.error_code == "evidence.selection"
    execution.grade.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "oversized"),
    [
        ("abcd", False),
        ("éé", False),
        ("🦊", False),
        ("abcde", True),
        ("ééé", True),
        ("🦊a", True),
    ],
)
async def test_utf8_item_budget_is_checked_before_provider(execution, text, oversized):
    request = _reflection_request(text)
    policy = request.task.evidence.model_copy(update={"max_file_size_bytes": 4})
    task = request.task.model_copy(update={"evidence": policy})
    prefix, raw = request.message.split("\n\n", 1)
    message = json.loads(raw)
    message["task"]["evidence_contract"] = policy.model_dump(mode="json")
    request = request.model_copy(
        update={"task": task, "message": f"{prefix}\n\n{json.dumps(message)}"}
    )
    execution.verify.return_value = replace(
        execution.result, grading_requests=[request]
    )
    finalized = await _execute(execution)
    if oversized:
        assert finalized.validation_result.error_code == "evidence.item_limit"
        execution.grade.assert_not_awaited()
    else:
        assert finalized.validation_result.is_valid is True
        execution.grade.assert_awaited_once_with(request.message)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing_criteria", "unknown_reference"])
async def test_invalid_decision_finalizes_as_response_validation(execution, invalid):
    updates = (
        {"criterion_results": []}
        if invalid == "missing_criteria"
        else {"evidence_refs": ["invented.md"]}
    )
    execution.grade.return_value = _decision().model_copy(update=updates)
    finalized = await _execute(execution)
    assert finalized.llm_error_type == "llm.response_validation"
    assert finalized.validation_result.verification_completed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["prepare", "verify", "grade", "finalize"])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_unexpected_errors_and_cancellation_reach_worker_without_retry(
    execution, stage, cancelled
):
    error = asyncio.CancelledError() if cancelled else RuntimeError("private detail")
    mock = getattr(execution, stage)
    mock.side_effect = error
    with pytest.raises(type(error)) as caught:
        await runner.execute_verification_attempt(
            execution.attempt.id, session_maker=execution.session_maker
        )
    assert caught.value is error
    mock.assert_awaited_once()
    if stage != "finalize":
        execution.finalize.assert_not_awaited()
