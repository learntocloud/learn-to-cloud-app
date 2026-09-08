"""Execute an already-claimed verification attempt in the API worker."""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE
from learn_to_cloud_shared.verification.engine import run_verification
from learn_to_cloud_shared.verification.evidence import (
    EVIDENCE_ERROR_CODES,
    EvidenceError,
)
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingDecisionPayload,
    validate_grading_request,
)
from learn_to_cloud_shared.verification.llm_grading import (
    apply_llm_grading_decisions,
    llm_grading_content_filtered_result,
    llm_grading_unavailable_result,
    validate_llm_grading_decision,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    finalize_verification_attempt,
    prepare_verification_attempt,
)
from learn_to_cloud_shared.verification_workflow import (
    LLM_ERROR_TYPES,
    VerificationRunResult,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.services.verification_grader import (
    LLM_RESPONSE_VALIDATION,
    ContentFilteredError,
    LLMGradingError,
    grade_evidence,
    missing_grading_config,
)

logger = logging.getLogger(f"{APP_LOGGER_NAMESPACE}.verification_runner")


def _grading_failed(
    run_result: VerificationRunResult, error_type: str
) -> VerificationRunResult:
    if error_type in EVIDENCE_ERROR_CODES:
        return replace(
            run_result,
            validation_result=EvidenceError(error_type).to_validation_result(),
            grading_requests=None,
        )
    if error_type not in LLM_ERROR_TYPES:
        error_type = "llm.unknown"
    logger.error(
        "verification.llm_grading.failed",
        extra={"error.type": error_type},
    )
    return llm_grading_unavailable_result(run_result, error_type=error_type)


async def _grade_result(run_result: VerificationRunResult) -> VerificationRunResult:
    validation = run_result.validation_result
    if (
        not validation.is_valid
        or not validation.verification_completed
        or not run_result.grading_requests
    ):
        return run_result
    if missing_grading_config():
        return _grading_failed(run_result, "llm.configuration")

    decisions: list[LLMGradingDecisionPayload] = []
    for request in run_result.grading_requests:
        try:
            validate_grading_request(request)
        except EvidenceError as exc:
            return _grading_failed(run_result, exc.code)
        except (KeyError, TypeError, ValueError):
            return _grading_failed(run_result, "evidence.selection")
        try:
            decision = await grade_evidence(request.message)
            validate_llm_grading_decision(
                request.task, decision, request.allowed_evidence_refs
            )
        except ValueError:
            return _grading_failed(run_result, LLM_RESPONSE_VALIDATION)
        except LLMGradingError as exc:
            return _grading_failed(run_result, exc.error_type)
        except ContentFilteredError:
            return llm_grading_content_filtered_result(run_result)
        decisions.append(
            LLMGradingDecisionPayload(task=request.task, decision=decision)
        )
    return apply_llm_grading_decisions(run_result, decisions)


async def execute_verification_attempt(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Prepare, verify, grade, and finalize once; unexpected errors reach the worker."""
    attempt = await prepare_verification_attempt(
        attempt_id, session_maker=session_maker
    )
    run_result = await run_verification(attempt)
    run_result = await _grade_result(run_result)
    await finalize_verification_attempt(run_result, session_maker=session_maker)
