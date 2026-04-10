"""Pull Request verification service.

The PR URL is server-derived from the authenticated user's GitHub
username, the requirement's repo, and the submitted PR number.
No URL parsing or ownership checks are needed.

Workflow (Agent Framework — edge conditions):
  **ValidationExecutor** → merged check + diff fetch
  **GraderAgent** (LLM) → grades diff via structured output
  **FeedbackExecutor** → applies guardrails, yields result

For LLM client infrastructure, see core/llm_client.py
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from agent_framework import (
    Agent,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from circuitbreaker import CircuitBreakerError

from core.config import get_settings
from core.llm_client import get_llm_chat_client
from schemas import HandsOnRequirement, TaskResult, ValidationResult
from services.verification.github_profile import (
    RETRIABLE_EXCEPTIONS,
    github_api_get,
    github_error_to_validation_result,
)
from services.verification.llm_base import (
    SUSPICIOUS_PATTERNS,
    VerificationError,
    build_grader_instructions,
    sanitize_feedback,
)
from services.verification.tasks.phase3 import (
    MAX_FILE_SIZE_BYTES,
    PrDiffGrade,
)

logger = logging.getLogger(__name__)


async def _fetch_pr_data(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch PR metadata."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    return (await github_api_get(url)).json()


class PrAnalysisError(VerificationError):
    """Raised when PR diff analysis fails."""


async def _fetch_pr_diff(owner: str, repo: str, pr_number: int) -> str:
    """Fetch the unified diff of a PR, size-limited and wrapped in safety tags."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    resp = await github_api_get(
        url, extra_headers={"Accept": "application/vnd.github.diff"}
    )
    diff_text = resp.text

    if len(diff_text.encode("utf-8")) > MAX_FILE_SIZE_BYTES:
        diff_text = diff_text[: MAX_FILE_SIZE_BYTES // 2]
        diff_text += "\n\n[DIFF TRUNCATED - exceeded size limit]"

    diff_lower = diff_text.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in diff_lower:
            logger.warning(
                "pr_verification.suspicious_pattern_in_diff",
                extra={"pattern": pattern, "owner": owner, "pr": pr_number},
            )
            break

    return f"<pr_diff>\n{diff_text}\n</pr_diff>"


# ─────────────────────────────────────────────────────────────────────────────
# Workflow executors
# ─────────────────────────────────────────────────────────────────────────────


class ValidationExecutor(Executor):
    """Checks the PR is merged and fetches the diff.

    The pr_url is server-derived (trusted) from the authenticated
    user's GitHub username + requirement's repo + PR number.
    """

    def __init__(
        self,
        *,
        pr_url: str,
        requirement: HandsOnRequirement,
    ) -> None:
        super().__init__(id="pr-validation")
        self._requirement = requirement
        # Extract owner/repo/number from trusted URL
        # Format: https://github.com/{owner}/{repo}/pull/{number}
        parts = pr_url.rstrip("/").split("/")
        self._owner = parts[3]
        self._repo = parts[4]
        self._pr_number = int(parts[6])

    @handler
    async def process(
        self,
        _msg: str,
        ctx: WorkflowContext[str | ValidationResult, ValidationResult],
    ) -> None:
        try:
            pr_data = await _fetch_pr_data(self._owner, self._repo, self._pr_number)
        except (
            CircuitBreakerError,
            httpx.HTTPStatusError,
            *RETRIABLE_EXCEPTIONS,
        ) as e:
            result = github_error_to_validation_result(
                e,
                event="pr_verification.api_error",
                context={
                    "owner": self._owner,
                    "repo": self._repo,
                    "pr": self._pr_number,
                },
            )
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                result = ValidationResult(
                    is_valid=False,
                    message=(
                        f"Pull request #{self._pr_number} not found. "
                        "Check the PR number and try again."
                    ),
                )
            await ctx.send_message(result)
            return

        if not pr_data.get("merged"):
            state = pr_data.get("state", "unknown")
            fail_msg = (
                f"PR #{self._pr_number} is still open. "
                "Merge it into main first, then resubmit."
                if state == "open"
                else f"PR #{self._pr_number} was closed without "
                "merging. Create a new PR, merge it, "
                "then submit that link."
            )
            await ctx.send_message(ValidationResult(is_valid=False, message=fail_msg))
            return

        # ── PR is valid and merged ───────────────────────────
        branch = pr_data.get("head", {}).get("ref", "unknown")
        ctx.set_state("pr_number", self._pr_number)
        ctx.set_state("branch_name", branch)

        if not self._requirement.grading_criteria:
            await ctx.yield_output(
                ValidationResult(
                    is_valid=True,
                    message=(
                        f"PR #{self._pr_number} verified! "
                        f"Merged from branch '{branch}'."
                    ),
                )
            )
            return

        try:
            diff = await _fetch_pr_diff(self._owner, self._repo, self._pr_number)
        except (
            CircuitBreakerError,
            httpx.HTTPStatusError,
            *RETRIABLE_EXCEPTIONS,
        ) as e:
            await ctx.send_message(
                github_error_to_validation_result(
                    e,
                    event="pr_verification.diff_error",
                    context={
                        "owner": self._owner,
                        "pr": self._pr_number,
                    },
                )
            )
            return

        ctx.set_state("diff", diff)
        await ctx.send_message(diff)


def _is_valid_pr(message: Any) -> bool:
    """Edge condition: validation passed, route to grader."""
    return not isinstance(message, ValidationResult)


def _is_invalid_pr(message: Any) -> bool:
    """Edge condition: validation failed, route to failure handler."""
    return isinstance(message, ValidationResult)


class GraderExecutor(Executor):
    """Grades a PR diff via LLM with structured output.

    Lazily initializes the LLM client inside the handler so the
    workflow can be built without requiring LLM configuration.
    The client is only created when the workflow actually routes
    a message here.
    """

    def __init__(self, *, requirement: HandsOnRequirement) -> None:
        super().__init__(id=f"pr-grader-{requirement.id}")
        self._requirement = requirement

    @handler
    async def process(
        self,
        diff: str,
        ctx: WorkflowContext[PrDiffGrade, None],
    ) -> None:
        chat_client = await get_llm_chat_client()
        agent = Agent(
            client=chat_client,
            instructions=build_grader_instructions(
                role="code reviewer",
                task_name=self._requirement.name,
                phase_label="Phase 3 capstone",
                content_tag="pr_diff",
                criteria=self._requirement.grading_criteria or [],
                pass_indicators=self._requirement.pass_indicators or [],
                fail_indicators=self._requirement.fail_indicators or [],
            ),
            name=f"pr-grader-{self._requirement.id}",
            default_options={"response_format": PrDiffGrade},
        )
        response = await agent.run([Message("user", [diff])])
        if response.value is None:
            raise PrAnalysisError("No structured output from PR grader", retriable=True)
        grade = (
            response.value
            if isinstance(response.value, PrDiffGrade)
            else PrDiffGrade.model_validate(response.value)
        )
        await ctx.send_message(grade)


class FeedbackExecutor(Executor):
    """Final executor in both valid and invalid PR paths.

    Handles two message types:
    - ``ValidationResult``: pass-through (invalid PR or deterministic result)
    - ``PrDiffGrade``: apply guardrails, build result
    """

    def __init__(self, *, requirement: HandsOnRequirement) -> None:
        super().__init__(id="pr-feedback")
        self._requirement = requirement

    @handler
    async def handle_validation_result(
        self,
        result: ValidationResult,
        ctx: WorkflowContext[None, ValidationResult],
    ) -> None:
        await ctx.yield_output(result)

    @handler
    async def handle_grade(
        self,
        grade: PrDiffGrade,
        ctx: WorkflowContext[None, ValidationResult],
    ) -> None:
        pr_number = ctx.get_state("pr_number", 0)
        branch_name = ctx.get_state("branch_name", "unknown")

        feedback = sanitize_feedback(grade.feedback)
        next_steps = sanitize_feedback(grade.next_steps)

        # Apply deterministic guardrails on the diff content.
        # Only check added/context lines — removed lines (starting with "-")
        # legitimately contain the old placeholder code the user deleted.
        diff: str = ctx.get_state("diff", "")
        added_or_context = "\n".join(
            line for line in diff.splitlines() if not line.startswith("-")
        ).lower()
        corrected_passed = grade.passed
        if grade.passed and self._requirement.fail_indicators:
            for indicator in self._requirement.fail_indicators:
                if indicator.lower() in added_or_context:
                    corrected_passed = False
                    feedback = (
                        "The PR diff still contains starter/placeholder code. "
                        "Replace the stub implementation with your own code."
                    )
                    next_steps = f"Remove or replace: {indicator}"
                    logger.info(
                        "pr_verification.guardrail_override",
                        extra={
                            "pr": pr_number,
                            "indicator": indicator,
                            "requirement": self._requirement.id,
                        },
                    )
                    break

        task_result = TaskResult(
            task_name=self._requirement.name,
            passed=corrected_passed,
            feedback=feedback,
            next_steps=next_steps,
        )

        if corrected_passed:
            message = (
                f"PR #{pr_number} verified! Merged from branch "
                f"'{branch_name}'. {feedback}"
            )
        else:
            message = (
                f"PR #{pr_number} was merged but doesn't fully implement "
                f"the required task. Review the feedback below."
            )

        logger.info(
            "pr_verification.workflow_completed",
            extra={
                "pr": pr_number,
                "requirement": self._requirement.id,
                "passed": corrected_passed,
            },
        )

        await ctx.yield_output(
            ValidationResult(
                is_valid=corrected_passed,
                message=message,
                username_match=True,
                task_results=[task_result],
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Workflow orchestration
# ─────────────────────────────────────────────────────────────────────────────


async def validate_pr(
    pr_url: str,
    requirement: HandsOnRequirement,
) -> ValidationResult:
    """Validate a GitHub Pull Request submission.

    The ``pr_url`` is server-derived from the authenticated user's
    GitHub username, the requirement's repo, and the submitted PR
    number.  No URL parsing or ownership checks are needed.

    Edge-condition routing::

        ValidationExecutor
            ├── valid  → GraderAgent → FeedbackExecutor
            └── invalid → FeedbackExecutor (pass-through)

    Args:
        pr_url: Server-derived PR URL (trusted).
        requirement: The requirement being verified.

    Returns:
        ValidationResult with pass/fail and a user-facing message.
    """
    validation = ValidationExecutor(
        pr_url=pr_url,
        requirement=requirement,
    )
    grader = GraderExecutor(requirement=requirement)
    feedback = FeedbackExecutor(requirement=requirement)

    workflow = (
        WorkflowBuilder(
            name="pr-diff-analysis",
            start_executor=validation,
            output_executors=[validation, feedback],
        )
        .add_edge(validation, grader, condition=_is_valid_pr)
        .add_edge(validation, feedback, condition=_is_invalid_pr)
        .add_edge(grader, feedback)
        .build()
    )

    timeout_seconds = get_settings().llm_cli_timeout
    logger.info(
        "pr_verification.workflow_started",
        extra={
            "pr_url": pr_url,
            "requirement": requirement.id,
            "timeout": timeout_seconds,
        },
    )

    async with asyncio.timeout(timeout_seconds):
        run_result = await workflow.run("Grade the PR diff.")

        outputs = run_result.get_outputs()
        if not outputs:
            raise PrAnalysisError(
                "No response from pr-diff-analysis workflow",
                retriable=True,
            )
        return outputs[0]
