"""AI-powered code verification service using GitHub Copilot SDK.

This module provides the business logic for Phase 2 code analysis verification.
It uses the Copilot SDK to analyze learners' forked repositories and verify
that they have correctly implemented the required tasks.

Required Tasks (from learntocloud/journal-starter):
1. Logging Setup - Configure logging in api/main.py
2a. GET Single Entry - Implement GET /entries/{entry_id} with 404 handling
2b. DELETE Entry - Implement DELETE /entries/{entry_id} with 404, 204 status
3. AI Analysis - Implement analyze_journal_entry() and POST /entries/{id}/analyze
5. Cloud CLI Setup - Uncomment CLI tool in .devcontainer/devcontainer.json

For Copilot client infrastructure, see core/copilot_client.py
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypedDict

import httpx
from circuitbreaker import CircuitBreakerError, circuit
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import get_settings
from core.copilot_client import CopilotClientError, get_copilot_client
from core.telemetry import track_operation
from core.wide_event import set_wide_event_fields
from schemas import TaskResult, ValidationResult


class TaskDefinition(TypedDict, total=False):
    """Type definition for a verification task."""

    id: str
    name: str
    file: str
    files: list[str]
    criteria: list[str]


# Task definitions for Phase 2 verification
PHASE2_TASKS: list[TaskDefinition] = [
    {
        "id": "logging-setup",
        "name": "Logging Setup",
        "file": "api/main.py",
        "criteria": [
            "Logger is configured (import logging or structlog)",
            "Log level is set appropriately",
            "Logger is used in the application",
        ],
    },
    {
        "id": "get-single-entry",
        "name": "GET Single Entry Endpoint",
        "file": "api/routers/journal_router.py",
        "criteria": [
            "GET /entries/{entry_id} endpoint exists",
            "Returns 404 when entry not found",
            "Uses proper response model",
        ],
    },
    {
        "id": "delete-entry",
        "name": "DELETE Entry Endpoint",
        "file": "api/routers/journal_router.py",
        "criteria": [
            "DELETE /entries/{entry_id} endpoint exists",
            "Returns 404 when entry not found",
            "Returns 204 No Content on successful deletion",
        ],
    },
    {
        "id": "ai-analysis",
        "name": "AI-Powered Entry Analysis",
        "files": ["api/services/llm_service.py", "api/routers/journal_router.py"],
        "criteria": [
            "analyze_journal_entry() function exists in llm_service.py",
            "Function makes LLM API call (OpenAI, Anthropic, Azure, etc.)",
            "POST /entries/{entry_id}/analyze endpoint exists",
            "Response includes sentiment, summary, and topics fields",
        ],
    },
    {
        "id": "cloud-cli-setup",
        "name": "Cloud CLI Setup",
        "file": ".devcontainer/devcontainer.json",
        "criteria": [
            "At least one cloud CLI is uncommented (Azure CLI, AWS CLI, gcloud)",
        ],
    },
]


class FetchGitHubFileParams(BaseModel):
    """Parameters for the fetch_github_file tool."""

    owner: str = Field(description="Repository owner (GitHub username)")
    repo: str = Field(description="Repository name")
    path: str = Field(description="File path within the repository")
    branch: str = Field(default="main", description="Branch name")


class CodeAnalysisError(Exception):
    """Raised when code analysis fails."""

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


def _extract_repo_info(repo_url: str) -> tuple[str, str]:
    """Extract owner and repo name from GitHub URL.

    Args:
        repo_url: GitHub repository URL

    Returns:
        Tuple of (owner, repo_name)

    Raises:
        ValueError: If URL is not a valid GitHub repository URL
    """
    # Handle various URL formats
    url = repo_url.strip().rstrip("/")

    # Normalize to https://github.com/owner/repo format
    patterns = [
        r"https?://github\.com/([^/]+)/([^/]+)/?.*",
        r"github\.com/([^/]+)/([^/]+)/?.*",
    ]

    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            owner, repo = match.groups()
            # Remove .git suffix if present
            repo = repo.removesuffix(".git")
            return owner, repo

    raise ValueError(f"Invalid GitHub repository URL: {repo_url}")


async def _fetch_github_file_content(
    owner: str, repo: str, path: str, branch: str = "main"
) -> str:
    """Fetch file content from GitHub repository.

    Args:
        owner: Repository owner
        repo: Repository name
        path: File path within repository
        branch: Branch name (default: main)

    Returns:
        File content as string

    Raises:
        httpx.HTTPStatusError: If file not found or request fails
    """
    settings = get_settings()

    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

    headers = {}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


def _build_verification_prompt(owner: str, repo: str) -> str:
    """Build the prompt for Copilot to verify task implementations.

    Args:
        owner: Repository owner (learner's GitHub username)
        repo: Repository name (should be journal-starter fork)

    Returns:
        Structured prompt for code analysis
    """
    tasks_description = "\n\n".join(
        f"**Task ID: `{task['id']}`** - {task['name']}\n"
        f"File(s): {task.get('file', ', '.join(task.get('files', [])))}\n"
        f"Criteria:\n" + "\n".join(f"  - {c}" for c in task["criteria"])
        for task in PHASE2_TASKS
    )

    # Build the exact task_id list for the response format
    task_ids = [task["id"] for task in PHASE2_TASKS]

    return f"""You are a code reviewer for the Learn to Cloud Journal API \
capstone project.
Analyze the repository {owner}/{repo} and verify whether the learner has \
completed all required tasks.

For each task, use the fetch_github_file tool to read the relevant files, \
then evaluate against the criteria.

## Required Tasks to Verify

{tasks_description}

## Instructions

1. For each task, fetch the relevant file(s) using the fetch_github_file tool
2. Analyze the code to determine if ALL criteria are met
3. Provide specific feedback about what was found or what's missing

## Response Format

CRITICAL: Use EXACTLY these task_id values: {task_ids}

You MUST respond with valid JSON in exactly this format:
```json
{{
  "tasks": [
    {{
      "task_id": "logging-setup",
      "passed": true,
      "feedback": "Logging configured using Python's logging module."
    }},
    {{
      "task_id": "get-single-entry",
      "passed": false,
      "feedback": "GET endpoint exists but missing 404 handling."
    }},
    {{
      "task_id": "delete-entry",
      "passed": false,
      "feedback": "..."
    }},
    {{
      "task_id": "ai-analysis",
      "passed": false,
      "feedback": "..."
    }},
    {{
      "task_id": "cloud-cli-setup",
      "passed": false,
      "feedback": "..."
    }}
  ]
}}
```

Include ALL 5 tasks with the EXACT task_id values shown above. Be specific in feedback.
"""


def _parse_analysis_response(response_text: str) -> list[dict[str, Any]]:
    """Parse the Copilot response to extract task results.

    Args:
        response_text: Raw response from Copilot

    Returns:
        List of task result dictionaries

    Raises:
        CodeAnalysisError: If response cannot be parsed
    """
    # Try to extract JSON from the response
    # Copilot may wrap it in markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON object
        json_match = re.search(r"\{.*\"tasks\".*\}", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise CodeAnalysisError(
                "Could not extract JSON from analysis response",
                retriable=True,
            )

    try:
        data = json.loads(json_str)
        if "tasks" not in data:
            raise CodeAnalysisError(
                "Response missing 'tasks' field",
                retriable=True,
            )
        return data["tasks"]
    except json.JSONDecodeError as e:
        raise CodeAnalysisError(
            f"Invalid JSON in analysis response: {e}",
            retriable=True,
        ) from e


def _build_task_results(
    parsed_tasks: list[dict[str, Any]],
) -> tuple[list[TaskResult], bool]:
    """Convert parsed task data to TaskResult objects.

    Args:
        parsed_tasks: List of task dictionaries from Copilot response

    Returns:
        Tuple of (list of TaskResult, all_passed boolean)
    """
    # Map task IDs to display names
    task_names = {task["id"]: task["name"] for task in PHASE2_TASKS}

    results = []
    all_passed = True

    for task in parsed_tasks:
        task_id = task.get("task_id", "unknown")
        passed = task.get("passed", False)
        feedback = task.get("feedback", "No feedback provided")

        if not passed:
            all_passed = False

        results.append(
            TaskResult(
                task_name=task_names.get(task_id, task_id),
                passed=passed,
                feedback=feedback,
            )
        )

    # Ensure all expected tasks have results
    found_ids = {t.get("task_id") for t in parsed_tasks}
    for task in PHASE2_TASKS:
        if task["id"] not in found_ids:
            all_passed = False
            results.append(
                TaskResult(
                    task_name=task["name"],
                    passed=False,
                    feedback="Task was not evaluated - please try again",
                )
            )

    return results, all_passed


RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    CopilotClientError,
    httpx.RequestError,
    httpx.TimeoutException,
)


@track_operation("code_analysis")
@circuit(
    failure_threshold=3,
    recovery_timeout=120,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="copilot_analysis_circuit",
)
@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential_jitter(initial=1, max=30),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _analyze_with_copilot(
    owner: str, repo: str, github_username: str
) -> ValidationResult:
    """Internal: Run code analysis with retry. Use analyze_repository_code() instead."""
    settings = get_settings()
    client = await get_copilot_client()

    # Collect the final response
    response_content = ""
    done = asyncio.Event()

    def on_event(event: Any) -> None:
        nonlocal response_content
        if event.type.value == "assistant.message":
            response_content = event.data.content
        elif event.type.value == "session.idle":
            done.set()

    # Import Copilot SDK types (lazy import to avoid import errors when SDK missing)
    from copilot import Tool, ToolInvocation, ToolResult
    from copilot.types import SessionConfig

    # Define the file fetching tool for Copilot to use
    async def fetch_github_file(invocation: ToolInvocation) -> ToolResult:
        """Tool handler for fetching GitHub file content."""
        args = invocation.get("arguments") or {}
        file_owner = args.get("owner", owner)
        file_repo = args.get("repo", repo)
        file_path = args.get("path", "")
        branch = args.get("branch", "main")

        set_wide_event_fields(
            copilot_tool_fetch_file=file_path,
            copilot_tool_repo=f"{file_owner}/{file_repo}",
        )

        try:
            content = await _fetch_github_file_content(
                file_owner, file_repo, file_path, branch
            )
            return ToolResult(
                textResultForLlm=content,
                resultType="success",
                sessionLog=f"Fetched {file_path} from {file_owner}/{file_repo}",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(
                    textResultForLlm=f"File not found: {file_path}",
                    resultType="success",
                    sessionLog=f"File not found: {file_path}",
                )
            return ToolResult(
                textResultForLlm=f"Error fetching file: {e}",
                resultType="failure",
                sessionLog=f"Error: {e}",
            )
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"Error fetching file: {e}",
                resultType="failure",
                sessionLog=f"Error: {e}",
            )

    file_tool = Tool(
        name="fetch_github_file",
        description="Fetch the contents of a file from a GitHub repository",
        parameters={
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner (GitHub username)",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository name",
                },
                "path": {
                    "type": "string",
                    "description": "File path within the repository",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch name (default: main)",
                    "default": "main",
                },
            },
            "required": ["path"],
        },
        handler=fetch_github_file,
    )

    # Create session with tool
    config = SessionConfig(
        model="gpt-5-mini",  # Free tier, supports structured outputs
        tools=[file_tool],
    )
    session = await client.create_session(config)

    try:
        session.on(on_event)

        # Build and send the verification prompt
        prompt = _build_verification_prompt(owner, repo)

        set_wide_event_fields(
            copilot_analysis_started=True,
            copilot_analysis_owner=owner,
            copilot_analysis_repo=repo,
        )

        await session.send({"prompt": prompt})

        # Wait for completion with timeout
        try:
            await asyncio.wait_for(done.wait(), timeout=settings.copilot_cli_timeout)
        except TimeoutError:
            set_wide_event_fields(
                copilot_error="timeout",
                copilot_timeout_seconds=settings.copilot_cli_timeout,
            )
            raise CodeAnalysisError(
                "Code analysis timed out. Please try again.",
                retriable=True,
            )

        # Parse the response
        if not response_content:
            raise CodeAnalysisError(
                "No response received from code analysis",
                retriable=True,
            )

        parsed_tasks = _parse_analysis_response(response_content)
        task_results, all_passed = _build_task_results(parsed_tasks)

        passed_count = sum(1 for t in task_results if t.passed)
        total_count = len(task_results)

        set_wide_event_fields(
            copilot_analysis_complete=True,
            copilot_tasks_passed=passed_count,
            copilot_tasks_total=total_count,
            copilot_all_passed=all_passed,
        )

        if all_passed:
            message = (
                f"Congratulations! All {total_count} tasks have been completed "
                "successfully. Your Journal API implementation meets all requirements."
            )
        else:
            message = (
                f"Completed {passed_count}/{total_count} tasks. "
                "Review the feedback below and try again after making improvements."
            )

        return ValidationResult(
            is_valid=all_passed,
            message=message,
            task_results=task_results,
        )

    finally:
        # Clean up session
        try:
            await session.destroy()
        except Exception:
            pass


async def analyze_repository_code(
    repo_url: str, github_username: str
) -> ValidationResult:
    """Analyze a learner's repository for Phase 2 task completion.

    This is the main entry point for code analysis verification.
    It connects to the Copilot CLI and uses AI to verify that the learner
    has correctly implemented all required tasks in their journal-starter fork.

    Args:
        repo_url: URL of the learner's forked repository
        github_username: The learner's GitHub username (for validation)

    Returns:
        ValidationResult with is_valid=True if all tasks pass,
        and detailed task_results for feedback.
    """
    try:
        owner, repo = _extract_repo_info(repo_url)
    except ValueError as e:
        return ValidationResult(
            is_valid=False,
            message=str(e),
        )

    # Verify the repo belongs to the expected user
    if owner.lower() != github_username.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"Repository owner '{owner}' does not match your GitHub username "
                f"'{github_username}'. Please submit your own fork."
            ),
            username_match=False,
        )

    set_wide_event_fields(
        code_analysis_owner=owner,
        code_analysis_repo=repo,
    )

    try:
        return await _analyze_with_copilot(owner, repo, github_username)
    except CircuitBreakerError:
        set_wide_event_fields(copilot_error="circuit_open")
        return ValidationResult(
            is_valid=False,
            message=(
                "Code analysis service is temporarily unavailable. "
                "Please try again in a few minutes."
            ),
            server_error=True,
        )
    except CodeAnalysisError as e:
        set_wide_event_fields(
            copilot_error="analysis_failed",
            copilot_error_detail=str(e),
            copilot_error_retriable=e.retriable,
        )
        return ValidationResult(
            is_valid=False,
            message=f"Code analysis failed: {e}",
            server_error=e.retriable,
        )
    except CopilotClientError as e:
        set_wide_event_fields(
            copilot_error="client_error",
            copilot_error_detail=str(e),
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "Unable to connect to code analysis service. " "Please try again later."
            ),
            server_error=True,
        )
