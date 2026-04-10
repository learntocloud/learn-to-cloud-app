"""AI-powered DevOps verification service.

This module provides Phase 5 verification: checking that learners have added
DevOps artifacts (Dockerfile, CI/CD, Terraform, K8s) to their journal-starter fork.

Workflow (Agent Framework — fan-out / fan-in):
  **PreflightExecutor** (start + output executor)
    → Fetches repo tree, runs static file check, fetches file contents
    → If static check fails → ``yield_output`` (short-circuit, no LLM call)
    → If static check passes → ``send_message`` (dispatch signal) to fan-out

  **DockerfileVerifier / CICDPipelineVerifier /
  TerraformVerifier / KubernetesVerifier** (fan-out branches)
    → Each receives dispatch signal, reads own files from workflow state
    → Calls own dedicated ``Agent`` with task-specific instructions
    → Applies per-task deterministic guardrails
    → ``send_message(TaskResult)`` downstream

  **AggregatorExecutor** (fan-in output executor)
    → Receives ``list[TaskResult]`` from all 4 branches
    → Builds final ``ValidationResult`` and ``yield_output``

For LLM client infrastructure, see core/llm_client.py
"""

from __future__ import annotations

import asyncio
import logging
from typing import Never

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
from core.github_client import get_github_client
from core.llm_client import get_llm_chat_client
from schemas import TaskResult, ValidationResult
from services.verification.github_profile import (
    RETRIABLE_EXCEPTIONS,
    get_github_headers,
    github_api_get,
    github_error_to_validation_result,
)
from services.verification.llm_base import (
    SUSPICIOUS_PATTERNS,
    VerificationError,
    build_grader_instructions,
    enforce_deterministic_guardrails,
    parse_structured_response,
    sanitize_feedback,
    validate_repo_url,
)
from services.verification.tasks.phase5 import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_CATEGORY,
    MAX_TOTAL_CONTENT_BYTES,
    PHASE5_TASKS,
    DevOpsTaskGrade,
    TaskDefinition,
)

logger = logging.getLogger(__name__)


class DevOpsAnalysisError(VerificationError):
    """Raised when DevOps analysis fails."""


# ─────────────────────────────────────────────────────────────────────────────
# Static helpers (pure functions, no workflow dependency)
# ─────────────────────────────────────────────────────────────────────────────


def _check_required_files(all_files: list[str]) -> list[TaskResult]:
    """Check each task's ``required_files`` against the full repo tree.

    Entries ending with ``/`` are directory prefixes — at least one
    file must exist under that path.  All other entries are exact
    file matches (case-insensitive).

    Returns:
        List of ``TaskResult`` failures.  Empty means all files exist.
    """
    all_files_lower = {f.lower() for f in all_files}
    failures: list[TaskResult] = []

    for task in PHASE5_TASKS:
        missing: list[str] = []
        for req in task["required_files"]:
            if req.endswith("/"):
                if not any(f.startswith(req.lower()) for f in all_files_lower):
                    missing.append(req)
            else:
                if req.lower() not in all_files_lower:
                    missing.append(req)

        if missing:
            first = missing[0]
            if first.endswith("/"):
                next_step = f"Add at least one file under {first} in your repository."
            else:
                next_step = f"Add {first} to your repository."
            failures.append(
                TaskResult(
                    task_name=task["name"],
                    passed=False,
                    feedback=(
                        "Required file(s) not found in repository: "
                        f"{', '.join(missing)}."
                    ),
                    next_steps=next_step,
                )
            )

    return failures


# ─────────────────────────────────────────────────────────────────────────────
# Repository tree and file fetching
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_repo_tree(owner: str, repo: str, branch: str = "main") -> list[str]:
    """Fetch the file tree of a GitHub repository.

    Uses the Git Trees API with ``recursive=1`` to get all files in one call.
    Retries transient failures via ``github_api_get``.

    Returns:
        List of file paths in the repository.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
    response = await github_api_get(url, params={"recursive": 1})

    tree_data = response.json()
    return [
        item["path"] for item in tree_data.get("tree", []) if item.get("type") == "blob"
    ]


def _filter_devops_files(all_files: list[str]) -> dict[str, list[str]]:
    """Filter repository files to DevOps-relevant paths.

    Exact-match patterns are collected first (guaranteed inclusion);
    directory patterns fill remaining slots up to MAX_FILES_PER_CATEGORY.
    This ensures critical named files (e.g. k8s/service.yaml) are never
    crowded out by large numbers of subdirectory files (e.g. k8s/monitoring/).

    Returns:
        Dict mapping task_id -> list of relevant file paths.
    """
    result: dict[str, list[str]] = {}

    for task in PHASE5_TASKS:
        exact_patterns = [p for p in task["path_patterns"] if not p.endswith("/")]
        dir_patterns = [p for p in task["path_patterns"] if p.endswith("/")]

        exact_matches: list[str] = []
        dir_matches: list[str] = []
        exact_set: set[str] = set()

        for file_path in all_files:
            matched_exact = False
            for pattern in exact_patterns:
                if file_path.lower() == pattern.lower():
                    exact_matches.append(file_path)
                    exact_set.add(file_path)
                    matched_exact = True
                    break
            if not matched_exact:
                for pattern in dir_patterns:
                    if file_path.lower().startswith(pattern.lower()):
                        dir_matches.append(file_path)
                        break

        # Exact matches always come first; directory matches fill remaining slots
        combined = exact_matches + [f for f in dir_matches if f not in exact_set]
        result[task["id"]] = combined[:MAX_FILES_PER_CATEGORY]

    return result


async def _fetch_file_content(
    owner: str, repo: str, path: str, branch: str = "main"
) -> str:
    """Fetch a single file's content from GitHub.

    Returns:
        File content wrapped in safety delimiters.
    """
    client = await get_github_client()

    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    headers = get_github_headers()

    response = await client.get(url, headers=headers)
    response.raise_for_status()

    content = response.text

    if len(content.encode("utf-8")) > MAX_FILE_SIZE_BYTES:
        content = content[: MAX_FILE_SIZE_BYTES // 2]
        content += "\n\n[FILE TRUNCATED - exceeded size limit]"

    content_lower = content.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in content_lower:
            logger.warning(
                "devops_analysis.suspicious_pattern",
                extra={"pattern": pattern, "file": path},
            )
            break

    return f'<file_content path="{path}">\n{content}\n</file_content>'


async def _fetch_all_devops_files(
    owner: str,
    repo: str,
    devops_files: dict[str, list[str]],
    branch: str = "main",
) -> dict[str, list[str]]:
    """Fetch all DevOps file contents in parallel.

    Returns:
        Dict mapping task_id -> list of file content strings.
    """
    fetch_tasks: list[tuple[str, str]] = []
    for task_id, paths in devops_files.items():
        for path in paths:
            fetch_tasks.append((task_id, path))

    if not fetch_tasks:
        return {task["id"]: [] for task in PHASE5_TASKS}

    async def _fetch_one(task_id: str, path: str) -> tuple[str, str | None]:
        try:
            content = await _fetch_file_content(owner, repo, path, branch)
            return (task_id, content)
        except httpx.HTTPStatusError:
            return (task_id, None)

    results = await asyncio.gather(
        *[_fetch_one(tid, p) for tid, p in fetch_tasks],
        return_exceptions=True,
    )

    grouped: dict[str, list[str]] = {task["id"]: [] for task in PHASE5_TASKS}
    total_bytes = 0

    for result in results:
        if isinstance(result, BaseException):
            continue
        task_id, content = result
        if content is None:
            continue

        content_size = len(content.encode("utf-8"))
        if total_bytes + content_size > MAX_TOTAL_CONTENT_BYTES:
            continue  # skip this file but keep trying smaller ones
        total_bytes += content_size
        grouped[task_id].append(content)

    return grouped


# ─────────────────────────────────────────────────────────────────────────────
# Per-task prompt construction
# ─────────────────────────────────────────────────────────────────────────────


def _build_task_instructions(task_def: TaskDefinition) -> str:
    """Build Agent system instructions specialized for one DevOps task."""
    return build_grader_instructions(
        role="DevOps instructor",
        task_name=task_def["name"],
        phase_label="Phase 5 capstone",
        content_tag="file_content",
        criteria=task_def["criteria"],
        pass_indicators=task_def.get("pass_indicators", []),
        fail_indicators=task_def.get("fail_indicators", []),
        extra_steps=["If <no_files_found /> appears, the task FAILS"],
    )


def _build_task_prompt(
    task_def: TaskDefinition,
    task_files: list[str],
) -> str:
    """Build the user prompt for a single task's Agent."""
    files_block = "\n\n".join(task_files) if task_files else "<no_files_found />"

    return (
        f"Grade the **{task_def['name']}** task "
        f"(task_id: `{task_def['id']}`).\n\n"
        f"## Files\n{files_block}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Workflow executors
# ─────────────────────────────────────────────────────────────────────────────


class PreflightExecutor(Executor):
    """Fetch repo tree, run static file check, prepare LLM content.

    Two possible outcomes:
      - **Static check fails** → ``yield_output(ValidationResult)`` directly.
        No downstream message is sent, so the fan-out Agents never run.
      - **Static check passes** → fetches file contents, stores them in
        workflow state, and ``send_message`` (dispatch signal) to fan-out.
    """

    def __init__(self, *, owner: str, repo: str) -> None:
        super().__init__(id="phase5-preflight")
        self._owner = owner
        self._repo = repo

    @handler
    async def process(
        self,
        _msg: str,
        ctx: WorkflowContext[str, ValidationResult],
    ) -> None:
        # ── Fetch repo tree ──────────────────────────────────
        logger.info(
            "devops_analysis.repo_tree_fetching",
            extra={
                "owner": self._owner,
                "repo": self._repo,
            },
        )
        try:
            all_files = await fetch_repo_tree(self._owner, self._repo)
        except (
            CircuitBreakerError,
            httpx.HTTPStatusError,
            *RETRIABLE_EXCEPTIONS,
        ) as e:
            result = github_error_to_validation_result(
                e,
                event="devops_analysis.repo_tree_error",
                context={
                    "owner": self._owner,
                    "repo": self._repo,
                },
            )
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                result = ValidationResult(
                    is_valid=False,
                    message=(
                        f"Repository '{self._owner}/{self._repo}' not found. "
                        "Make sure the repository is public."
                    ),
                )
            await ctx.yield_output(result)
            return

        logger.info(
            "devops_analysis.repo_tree_fetched",
            extra={
                "owner": self._owner,
                "repo": self._repo,
                "total_files": len(all_files),
            },
        )

        # ── Static existence check ───────────────────────────
        existence_failures = _check_required_files(all_files)

        if existence_failures:
            logger.info(
                "devops_analysis.skipped_llm",
                extra={
                    "owner": self._owner,
                    "repo": self._repo,
                    "reason": "required_files_missing",
                    "failed_tasks": [f.task_name for f in existence_failures],
                },
            )
            failed_count = len(existence_failures)
            total = len(PHASE5_TASKS)
            message = (
                f"{failed_count} of {total} tasks are missing required files. "
                "Add the missing files listed below, then re-submit."
            )
            await ctx.yield_output(
                ValidationResult(
                    is_valid=False,
                    message=message,
                    task_results=existence_failures,
                )
            )
            return

        # ── Fetch file contents ──────────────────────────────
        devops_files = _filter_devops_files(all_files)
        total_fetch = sum(len(v) for v in devops_files.values())
        logger.info(
            "devops_analysis.file_fetch_started",
            extra={
                "owner": self._owner,
                "repo": self._repo,
                "files_to_fetch": total_fetch,
                "files_per_task": {
                    tid: len(paths) for tid, paths in devops_files.items()
                },
            },
        )

        file_contents = await _fetch_all_devops_files(
            self._owner, self._repo, devops_files
        )

        fetched_per_task = {
            tid: len(contents) for tid, contents in file_contents.items()
        }
        logger.info(
            "devops_analysis.file_fetch_completed",
            extra={
                "owner": self._owner,
                "repo": self._repo,
                "fetched_per_task": fetched_per_task,
            },
        )

        ctx.set_state("file_contents", file_contents)

        # ── Dispatch to fan-out branches ─────────────────────
        logger.info(
            "devops_analysis.fan_out_dispatching",
            extra={
                "owner": self._owner,
                "repo": self._repo,
                "verifier_count": 4,
            },
        )
        await ctx.send_message("grade")


class TaskVerifier(Executor):
    """Fan-out branch: grades one DevOps task via a dedicated Agent.

    Lazily creates the LLM client and Agent inside the handler so the
    workflow can be constructed without requiring LLM configuration.

    On receiving the dispatch signal the handler:
      1. Reads its task's file contents from workflow state.
      2. Builds a per-task prompt with only the relevant files.
      3. Calls a dedicated ``Agent.run()`` for structured grading.
      4. Applies deterministic guardrails on the single grade.
      5. Sends the resulting ``TaskResult`` downstream.
    """

    def __init__(self, *, task_def: TaskDefinition) -> None:
        super().__init__(id=f"verifier-{task_def['id']}")
        self._task_def = task_def

    @handler
    async def process(
        self,
        _msg: str,
        ctx: WorkflowContext[TaskResult],
    ) -> None:
        task_id = self._task_def["id"]
        task_name = self._task_def["name"]
        file_contents: dict[str, list[str]] = ctx.get_state("file_contents", {})
        task_files = file_contents.get(task_id, [])

        logger.info(
            "devops_analysis.task_grading_started",
            extra={
                "task_id": task_id,
                "task_name": task_name,
                "file_count": len(task_files),
            },
        )

        prompt = _build_task_prompt(self._task_def, task_files)

        chat_client = await get_llm_chat_client()
        agent = Agent(
            client=chat_client,
            instructions=_build_task_instructions(self._task_def),
            name=f"grader-{self._task_def['id']}",
        )
        response = await agent.run(
            [Message("user", [prompt])],
            options={"response_format": DevOpsTaskGrade},
        )

        grade = parse_structured_response(
            response,
            DevOpsTaskGrade,
            DevOpsAnalysisError,
            f"devops_analysis.{task_id}",
        )

        llm_passed = grade.passed

        # Per-task deterministic guardrails
        raw_content = "".join(task_files) if task_files else "<no_files_found />"
        corrected = enforce_deterministic_guardrails(
            grades=[grade],
            task_definitions=[self._task_def],
            get_file_content=lambda _td: raw_content,
            suspicious_patterns=SUSPICIOUS_PATTERNS,
            grade_factory=DevOpsTaskGrade,
            service_name="devops_analysis",
        )
        grade = corrected[0]

        if llm_passed != grade.passed:
            logger.info(
                "devops_analysis.task_guardrail_override",
                extra={
                    "task_id": task_id,
                    "task_name": task_name,
                    "llm_passed": llm_passed,
                    "final_passed": grade.passed,
                },
            )

        feedback = sanitize_feedback(grade.feedback)
        next_steps = sanitize_feedback(getattr(grade, "next_steps", "") or "")

        logger.info(
            "devops_analysis.task_grading_completed",
            extra={
                "task_id": task_id,
                "task_name": task_name,
                "passed": grade.passed,
            },
        )

        await ctx.send_message(
            TaskResult(
                task_name=self._task_def["name"],
                passed=grade.passed,
                feedback=feedback,
                next_steps=next_steps,
            )
        )


class AggregatorExecutor(Executor):
    """Fan-in: collects ``TaskResult`` from all branches, builds final output.

    Receives a ``list[TaskResult]`` (aggregated by the fan-in edge group)
    and yields a single ``ValidationResult``.
    """

    def __init__(self, *, owner: str, repo: str) -> None:
        super().__init__(id="phase5-aggregator")
        self._owner = owner
        self._repo = repo

    @handler
    async def process(
        self,
        results: list[TaskResult],
        ctx: WorkflowContext[Never, ValidationResult],
    ) -> None:
        # Preserve task definition order
        task_order = {t["name"]: i for i, t in enumerate(PHASE5_TASKS)}
        sorted_results = sorted(results, key=lambda r: task_order.get(r.task_name, 999))

        passed_count = sum(1 for t in sorted_results if t.passed)
        total_count = len(PHASE5_TASKS)
        all_passed = passed_count == total_count

        if all_passed:
            message = (
                f"All {total_count} DevOps tasks verified! "
                "Your journal-starter fork has proper "
                "containerization, CI/CD, Terraform, and "
                "Kubernetes artifacts."
            )
        else:
            message = (
                f"Completed {passed_count}/{total_count} tasks. "
                "Review the feedback below and try again "
                "after making improvements."
            )

        logger.info(
            "devops_analysis.completed",
            extra={
                "owner": self._owner,
                "repo": self._repo,
                "passed": passed_count,
                "total": len(sorted_results),
                "all_passed": all_passed,
                "task_grades": {t.task_name: t.passed for t in sorted_results},
            },
        )

        await ctx.yield_output(
            ValidationResult(
                is_valid=all_passed,
                message=message,
                task_results=sorted_results,
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Workflow orchestration
# ─────────────────────────────────────────────────────────────────────────────


async def _run_devops_workflow(owner: str, repo: str) -> ValidationResult:
    """Run the full Phase 5 DevOps verification workflow.

    Builds a fan-out / fan-in Agent Framework workflow::

        PreflightExecutor ──fan-out──→ TaskVerifier(dockerfile)       ─┐
              │                       → TaskVerifier(cicd-pipeline)    ─┤ fan-in
              │                       → TaskVerifier(terraform-iac)    ─┤ ──→ Aggregator
              │                       → TaskVerifier(k8s-manifests)    ─┘
              │
              └── yield_output (short-circuit on static check failure)
    """
    preflight = PreflightExecutor(owner=owner, repo=repo)

    verifiers = [TaskVerifier(task_def=task) for task in PHASE5_TASKS]

    aggregator = AggregatorExecutor(owner=owner, repo=repo)

    workflow = (
        WorkflowBuilder(
            name="phase5-devops-analysis",
            start_executor=preflight,
            output_executors=[preflight, aggregator],
        )
        .add_fan_out_edges(preflight, verifiers)
        .add_fan_in_edges(verifiers, aggregator)
        .build()
    )

    timeout_seconds = get_settings().llm_cli_timeout
    logger.info(
        "devops_analysis.workflow_started",
        extra={
            "owner": owner,
            "repo": repo,
            "timeout": timeout_seconds,
        },
    )

    async with asyncio.timeout(timeout_seconds):
        run_result = await workflow.run(
            "Analyze the repository artifacts and grade all 4 tasks."
        )

        outputs = run_result.get_outputs()
        if not outputs:
            raise DevOpsAnalysisError(
                "No response from phase5-devops-analysis workflow",
                retriable=True,
            )
        return outputs[0]


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


async def analyze_devops_repository(
    repo_url: str,
    github_username: str,
    expected_repo_name: str | None = None,
) -> ValidationResult:
    """Analyze a learner's repository for Phase 5 DevOps artifact completion.

    This is the main entry point for DevOps verification.
    Validates the repo URL / ownership, then delegates to
    :func:`_run_devops_workflow` which orchestrates the full
    Agent Framework pipeline.
    """
    logger.info(
        "devops_analysis.started",
        extra={
            "repo_url": repo_url,
            "github_username": github_username,
        },
    )

    result = validate_repo_url(repo_url, github_username, expected_repo_name)
    if isinstance(result, ValidationResult):
        return result
    owner, repo = result

    return await _run_devops_workflow(owner, repo)
