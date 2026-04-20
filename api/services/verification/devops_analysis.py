"""Phase 5 DevOps verification — checks that learners have added
Dockerfile, CI/CD, Terraform, and K8s artifacts to their journal-starter fork.
"""

from __future__ import annotations

import asyncio

import httpx
from opentelemetry import trace

from core.github_client import get_github_client
from schemas import TaskResult, ValidationResult
from services.verification.github_profile import (
    RETRIABLE_EXCEPTIONS,
    get_github_headers,
    github_api_get,
    github_error_to_validation_result,
)
from services.verification.tasks.phase5 import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_CATEGORY,
    MAX_TOTAL_CONTENT_BYTES,
    PHASE5_TASKS,
    TaskDefinition,
)

tracer = trace.get_tracer(__name__)

# Patterns that suggest prompt injection attempts.
# Logged as warnings for monitoring.
_SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "mark as passed",
    "override",
    "system prompt",
]


class DevOpsAnalysisError(Exception):
    """Raised when DevOps analysis fails."""


# ─────────────────────────────────────────────────────────────────────────────
# Static helpers (pure functions)
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


def _check_task_indicators(
    task_def: TaskDefinition,
    file_contents: list[str],
) -> TaskResult:
    """Check pass/fail indicators against file contents for one task."""
    task_name = task_def["name"]
    combined = "\n".join(file_contents) if file_contents else ""
    combined_lower = combined.lower()

    # Check fail indicators first (any match → fail)
    for indicator in task_def.get("fail_indicators", []):
        if indicator.lower() in combined_lower:
            return TaskResult(
                task_name=task_name,
                passed=False,
                feedback=f"Found disallowed pattern: {indicator}",
                next_steps=f"Remove or replace: {indicator}",
            )

    # Check pass indicators (threshold-based)
    pass_indicators = task_def.get("pass_indicators", [])
    min_count = task_def.get("min_pass_count", 1)

    if not pass_indicators:
        return TaskResult(
            task_name=task_name,
            passed=True,
            feedback="No specific indicators required.",
            next_steps="",
        )

    matched: list[str] = []
    missing: list[str] = []
    for indicator in pass_indicators:
        if indicator.lower() in combined_lower:
            matched.append(indicator)
        else:
            missing.append(indicator)

    if len(matched) >= min_count:
        return TaskResult(
            task_name=task_name,
            passed=True,
            feedback=(
                f"Found {len(matched)}/{len(pass_indicators)} "
                f"implementation indicators."
            ),
            next_steps="",
        )

    return TaskResult(
        task_name=task_name,
        passed=False,
        feedback=(
            f"Found {len(matched)}/{len(pass_indicators)} indicators "
            f"(need at least {min_count}). "
            f"Missing: {', '.join(missing[:5])}"
        ),
        next_steps=(
            f"Add the missing implementation. Look for: {missing[0]}"
            if missing
            else "Review the requirements."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Repository tree and file fetching
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_repo_tree(owner: str, repo: str, branch: str = "main") -> list[str]:
    """Fetch the file tree of a GitHub repository.

    Uses the Git Trees API with ``recursive=1`` to get all files in one call.

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
    """Fetch a single file's raw content from GitHub."""
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
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern in content_lower:
            span = trace.get_current_span()
            span.add_event(
                "suspicious_pattern",
                {"pattern": pattern, "file": path},
            )
            break

    return content


async def _fetch_all_devops_files(
    owner: str,
    repo: str,
    devops_files: dict[str, list[str]],
    branch: str = "main",
) -> dict[str, list[str]]:
    """Fetch all DevOps file contents in parallel.

    Returns:
        Dict mapping task_id -> list of raw file content strings.
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
            continue
        total_bytes += content_size
        grouped[task_id].append(content)

    return grouped


# ─────────────────────────────────────────────────────────────────────────────
# Main workflow
# ─────────────────────────────────────────────────────────────────────────────


async def run_devops_workflow(owner: str, repo: str) -> ValidationResult:
    """Run the full Phase 5 DevOps verification."""
    with tracer.start_as_current_span(
        "devops_verification",
        attributes={
            "github.owner": owner,
            "github.repo": repo,
        },
    ) as span:
        # ── Step 1: Fetch repo tree ──────────────────────────────
        try:
            all_files = await fetch_repo_tree(owner, repo)
        except (
            httpx.HTTPStatusError,
            *RETRIABLE_EXCEPTIONS,
        ) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                span.set_attribute("verification.passed", False)
                span.set_attribute("verification.reason", "repo_not_found")
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Repository '{owner}/{repo}' not found. "
                        "Make sure the repository is public."
                    ),
                )
            span.record_exception(e)
            return github_error_to_validation_result(
                e,
                event="devops_analysis.repo_tree_error",
                context={"owner": owner, "repo": repo},
            )

        span.set_attribute("repo.total_files", len(all_files))

        # ── Step 2: Check required files exist ───────────────────
        existence_failures = _check_required_files(all_files)

        if existence_failures:
            span.set_attribute("verification.passed", False)
            span.set_attribute("verification.reason", "missing_files")
            span.set_attribute(
                "verification.failed_tasks",
                ",".join(f.task_name for f in existence_failures),
            )
            failed_count = len(existence_failures)
            total = len(PHASE5_TASKS)
            return ValidationResult(
                is_valid=False,
                message=(
                    f"{failed_count} of {total} tasks are missing required files. "
                    "Add the missing files listed below, then re-submit."
                ),
                task_results=existence_failures,
            )

        # ── Step 3: Fetch file contents ──────────────────────────
        devops_files = _filter_devops_files(all_files)
        file_contents = await _fetch_all_devops_files(owner, repo, devops_files)

        span.set_attribute(
            "repo.fetched_files",
            sum(len(v) for v in file_contents.values()),
        )

        # ── Step 4: Run indicator checks per task ────────────────
        task_results: list[TaskResult] = []
        for task_def in PHASE5_TASKS:
            task_files = file_contents.get(task_def["id"], [])
            result = _check_task_indicators(task_def, task_files)
            task_results.append(result)

        # ── Step 5: Aggregate results ────────────────────────────
        passed_count = sum(1 for t in task_results if t.passed)
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

        span.set_attribute("verification.passed", all_passed)
        span.set_attribute("verification.passed_count", passed_count)
        span.set_attribute("verification.total_count", total_count)

        return ValidationResult(
            is_valid=all_passed,
            message=message,
            task_results=task_results,
        )
