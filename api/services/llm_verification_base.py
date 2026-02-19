"""Shared utilities for LLM-powered verification services.

Provides common patterns used across verification services
(Phase 3 code_verification, Phase 5 devops_verification,
Phase 6 security_verification):

- GitHub URL parsing and ownership validation
- LLM structured response parsing (generic over response type)
- Task result builder from LLM grades
- Feedback sanitization for safe display
- Prompt-injection detection patterns
- Retriable exception types for circuit breakers / retries

Phase-specific concerns stay in their respective modules:
- Phase 3: deterministic guardrails, content filter checks, allowlisted file fetching
- Phase 5: tree-based file discovery, parallel DevOps file fetching
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx

from core.llm_client import LLMClientError
from schemas import TaskResult, ValidationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retriable exception types shared by circuit breakers and retry decorators
# ---------------------------------------------------------------------------

RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    LLMClientError,
    httpx.RequestError,
    httpx.TimeoutException,
)

# ---------------------------------------------------------------------------
# Prompt-injection detection patterns
# ---------------------------------------------------------------------------

SUSPICIOUS_PATTERNS: tuple[str, ...] = (
    "ignore all previous",
    "ignore prior instructions",
    "disregard above",
    "system prompt",
    "you are now",
    "new instructions",
    "forget everything",
    "json```",
    "mark all tasks as passed",
    "mark as passed",
    "override grading",
    "always return true",
    "always pass",
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "[system]",
    "respond with json",
)


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class VerificationError(Exception):
    """Base exception for LLM verification failures.

    Attributes:
        retriable: ``True`` when the caller should retry (transient error).
    """

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------


def extract_repo_info(repo_url: str) -> tuple[str, str]:
    """Extract owner and repo name from a GitHub URL.

    Handles common variants: ``https://``, ``http://``, ``www.github.com``,
    trailing slashes, ``.git`` suffixes, sub-paths, query strings, and
    fragment identifiers.

    Raises:
        ValueError: If *repo_url* is not a valid GitHub repository URL.
    """
    url = repo_url.strip()
    if not url:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    # Ensure a scheme so urlparse can parse the host correctly.
    if not url.startswith(("http://", "https://")):
        # Bare "github.com/…" or "www.github.com/…"
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    # Accept github.com and www.github.com
    if host not in ("github.com", "www.github.com"):
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    # Path segments: filter out empty strings from leading/trailing slashes
    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    owner = segments[0]
    repo = segments[1].removesuffix(".git")

    return owner, repo


def validate_repo_url(
    repo_url: str, github_username: str
) -> tuple[str, str] | ValidationResult:
    """Parse a GitHub URL and verify the repo belongs to *github_username*.

    Returns:
        ``(owner, repo)`` on success, or a :class:`ValidationResult` error.
    """
    try:
        owner, repo = extract_repo_info(repo_url)
    except ValueError as e:
        return ValidationResult(is_valid=False, message=str(e))

    if owner.lower() != github_username.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"Repository owner '{owner}' does not match your GitHub username "
                f"'{github_username}'. Please submit your own repository."
            ),
            username_match=False,
        )

    return owner, repo


# ---------------------------------------------------------------------------
# Feedback sanitization
# ---------------------------------------------------------------------------


def sanitize_feedback(feedback: str | None) -> str:
    """Sanitize LLM-generated feedback before displaying to users.

    Removes HTML tags, code blocks, and URLs while preserving
    educational value.
    """
    if not feedback or not isinstance(feedback, str):
        return "No feedback provided"

    max_length = 500
    if len(feedback) > max_length:
        feedback = feedback[:max_length].rsplit(" ", 1)[0] + "..."

    feedback = re.sub(r"<[^>]+>", "", feedback)
    feedback = re.sub(r"```[\s\S]*?```", "[code snippet]", feedback)
    feedback = re.sub(r"https?://\S+", "[link removed]", feedback)

    return feedback.strip() or "No feedback provided"


# ---------------------------------------------------------------------------
# Generic structured-response parsing
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402 (grouped for readability)

ResponseT = TypeVar("ResponseT", bound=BaseModel)


def parse_structured_response(
    result: Any,
    response_type: type[ResponseT],
    error_class: type[VerificationError],
    service_name: str,
) -> ResponseT:
    """Extract a Pydantic structured response from an agent result.

    Tries ``result.value`` first (native structured output), then falls
    back to JSON-parsing ``result.text``.

    Args:
        result: The ``AgentRunResponse`` from ``ChatAgent.run()``.
        response_type: The Pydantic model to validate against.
        error_class: The :class:`VerificationError` subclass to raise on failure.
        service_name: Human-readable service name for error messages.

    Raises:
        VerificationError (subclass): When the response cannot be parsed.
    """
    if result.value is not None:
        if isinstance(result.value, response_type):
            return result.value
        try:
            return response_type.model_validate(result.value)
        except (ValueError, TypeError):
            pass

    text = result.text
    if not text:
        raise error_class(
            f"No response received from {service_name}",
            retriable=True,
        )

    try:
        return response_type.model_validate_json(text)
    except (ValueError, TypeError) as e:
        raise error_class(
            f"Could not parse analysis response: {e}",
            retriable=True,
        ) from e


# ---------------------------------------------------------------------------
# Generic task-result builder
# ---------------------------------------------------------------------------


def build_task_results(
    grades: list[Any],
    task_definitions: list[Any],
) -> tuple[list[TaskResult], bool]:
    """Convert LLM grade objects to :class:`TaskResult` list.

    Sanitizes feedback and fills in ``"not evaluated"`` entries for any
    tasks missing from *grades*.

    Args:
        grades: Objects with ``task_id``, ``passed``, and ``feedback`` attrs.
        task_definitions: Dicts (or TypedDicts) with ``"id"`` and ``"name"`` keys.

    Returns:
        ``(results, all_passed)`` tuple.
    """
    task_names = {task["id"]: task["name"] for task in task_definitions}
    valid_task_ids = set(task_names.keys())

    results: list[TaskResult] = []
    all_passed = True

    for grade in grades:
        if grade.task_id not in valid_task_ids:
            continue

        feedback = sanitize_feedback(grade.feedback)

        if not grade.passed:
            all_passed = False

        results.append(
            TaskResult(
                task_name=task_names.get(grade.task_id, grade.task_id),
                passed=grade.passed,
                feedback=feedback,
            )
        )

    # Ensure all expected tasks have results
    found_ids = {g.task_id for g in grades if g.task_id in valid_task_ids}
    for task in task_definitions:
        if task["id"] not in found_ids:
            all_passed = False
            results.append(
                TaskResult(
                    task_name=task["name"],
                    passed=False,
                    feedback="Task was not evaluated — please try again",
                )
            )

    return results, all_passed
