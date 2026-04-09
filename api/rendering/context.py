"""Progress and feedback rendering helpers for route handlers.

Centralises the data-shaping that routes perform before passing
context to Jinja2 templates. Keeps route functions thin and
avoids duplicated dict-building logic.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from models import SubmissionType
from services.verification.url_derivation import (
    derive_submission_value,
    fork_name_from_required_repo,
    is_derivable,
)

if TYPE_CHECKING:
    from schemas import Phase, PhaseDetailProgress, TaskResult, Topic

# ── FAQ content ──────────────────────────────────────────────
# Stored here (rendering layer) rather than in templates or routes.
# Each entry is (question, answer_html).

_SPONSOR_LINK = (
    '<a href="https://github.com/sponsors/madebygps" target="_blank"'
    ' rel="noopener noreferrer"'
    ' class="text-blue-600 dark:text-blue-400 underline">sponsor us on GitHub</a>'
)
_DISCUSSIONS_LINK = (
    '<a href="https://github.com/learntocloud/learn-to-cloud-app/discussions"'
    ' target="_blank" rel="noopener noreferrer"'
    ' class="text-blue-600 dark:text-blue-400 underline">GitHub Discussions</a>'
)

FAQS: list[tuple[str, str]] = [
    (
        "What is Learn to Cloud?",
        "Learn to Cloud is a structured, hands-on guide to learning cloud computing."
        " It takes you from the fundamentals through advanced topics with practical"
        " exercises verified by our platform.",
    ),
    (
        "Is it free?",
        f"Yes! Learn to Cloud is completely free. If you find it helpful, you can"
        f" {_SPONSOR_LINK} to support the project.",
    ),
    (
        "Do I need prior experience?",
        "No prior cloud experience is needed. Phase 0 covers prerequisites like"
        " Linux, networking, and programming fundamentals.",
    ),
    (
        "How long does it take?",
        "It depends on your pace and background. Most learners complete all phases"
        " in 3-6 months of part-time study.",
    ),
    (
        "Can I skip phases?",
        "You can read any phase, but hands-on verification builds on earlier phases."
        " We recommend following the sequence.",
    ),
    (
        "How does hands-on verification work?",
        "Each phase has practical tasks — creating a GitHub profile, deploying an"
        " API, analyzing code. You submit proof (URLs, tokens, or code) and our"
        " platform verifies it automatically.",
    ),
    (
        "What data do you collect about me?",
        "We only store information from your public GitHub profile: your GitHub user"
        " ID, username, display name, and avatar URL. We do not collect your email"
        " address, password, or any other personal information.",
    ),
    (
        "Can I delete my account?",
        'Yes. Go to your <a href="/account" class="text-blue-600 dark:text-blue-400'
        ' underline">Account page</a>. Clicking "Delete Account" will permanently'
        " remove your profile and all associated data (progress and submissions).",
    ),
    (
        "How can I support Learn to Cloud?",
        f"You can {_SPONSOR_LINK}, share the project with others, or help fellow"
        f" learners in our {_DISCUSSIONS_LINK}.",
    ),
    (
        "Why is only GitHub login available?",
        "Our hands-on verification system relies heavily on GitHub — you submit"
        " GitHub repos, profiles, and deployments as proof of your work, and we"
        " verify them automatically. Plus, if you're serious about learning cloud,"
        " you need a GitHub account anyway. It's an essential tool for any cloud or"
        " DevOps role.",
    ),
]

# ── Dashboard help links ─────────────────────────────────────

_X_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">'
    '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817'
    "L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52"
    'h1.833L7.084 4.126H5.117z"/></svg>'
)

HELP_LINKS: list[dict[str, str]] = [
    {
        "url": "https://github.com/learntocloud/learn-to-cloud-app/discussions",
        "label": "Join the Community",
        "color": "text-indigo-500 dark:text-indigo-400",
        "icon": (
            '<svg class="h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none"'
            ' viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">'
            '<path stroke-linecap="round" stroke-linejoin="round"'
            ' d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 0 1-2-2V6'
            "a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-4l-3 3-3-3z"
            '"/></svg>'
        ),
    },
    {
        "url": "https://x.com/madebygps",
        "label": "Follow @madebygps",
        "color": "text-gray-800 dark:text-gray-200",
        "icon": _X_SVG,
    },
    {
        "url": "https://x.com/learntocloud",
        "label": "Follow @learntocloud",
        "color": "text-gray-800 dark:text-gray-200",
        "icon": _X_SVG,
    },
    {
        "url": "https://github.com/learntocloud/learn-to-cloud-app/issues/new",
        "label": "Report an Issue",
        "color": "text-orange-500 dark:text-orange-400",
        "icon": (
            '<svg class="h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none"'
            ' viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">'
            '<path stroke-linecap="round" stroke-linejoin="round"'
            ' d="M12 9v2m0 4h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/></svg>'
        ),
    },
]


def build_progress_dict(completed: int, total: int) -> dict[str, int]:
    """Build a progress dict for template rendering.

    Returns:
        Dict with ``completed``, ``total``, and ``percentage`` keys.
    """
    return {
        "completed": completed,
        "total": total,
        "percentage": round(completed / total * 100) if total > 0 else 0,
    }


def build_phase_topics(
    phase: Phase, detail: PhaseDetailProgress
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build template-ready topic list and overall progress for a phase page.

    Merges topic metadata from content with per-topic progress data.

    Returns:
        ``(topics, progress)`` — topics is a list of dicts with ``name``,
        ``slug``, and ``progress`` keys; progress is a dict with
        ``percentage``, ``steps_completed``, and ``steps_required`` keys.
    """
    topics: list[dict[str, Any]] = []
    for t in phase.topics:
        tp = detail.topic_progress.get(t.id)
        topics.append(
            {
                "name": t.name,
                "slug": t.slug,
                "progress": (
                    {"completed": tp.steps_completed, "total": tp.steps_total}
                    if tp
                    else None
                ),
            }
        )

    progress = {
        "percentage": detail.percentage,
        "steps_completed": detail.steps_completed,
        "steps_required": detail.steps_total,
    }

    return topics, progress


def build_feedback_tasks(
    feedback_json: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Parse feedback JSON into a template-ready task list.

    Args:
        feedback_json: JSON string of task results from a submission.

    Returns:
        ``(feedback_tasks, passed_count)`` tuple.
    """
    tasks: list[dict[str, Any]] = []
    passed = 0
    if not feedback_json:
        return tasks, passed

    try:
        parsed = json.loads(feedback_json)
    except (json.JSONDecodeError, TypeError):
        return tasks, passed

    for task_data in parsed:
        tasks.append(
            {
                "name": task_data.get("task_name", ""),
                "passed": task_data.get("passed", False),
                "message": task_data.get("feedback", ""),
                "next_steps": task_data.get("next_steps", ""),
            }
        )
        if task_data.get("passed"):
            passed += 1

    return tasks, passed


def build_feedback_tasks_from_results(
    task_results: list[TaskResult] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Build a template-ready task list from task result objects.

    Args:
        task_results: List of objects with ``task_name``, ``passed``,
            and ``feedback`` attributes.

    Returns:
        ``(feedback_tasks, passed_count)`` tuple.
    """
    tasks: list[dict[str, Any]] = []
    passed = 0
    if not task_results:
        return tasks, passed

    for task in task_results:
        tasks.append(
            {
                "name": task.task_name,
                "passed": task.passed,
                "message": task.feedback,
                "next_steps": task.next_steps,
            }
        )
        if task.passed:
            passed += 1

    return tasks, passed


def build_requirement_card_context(
    *,
    requirement: Any,
    github_username: str | None,
    submission: Any = None,
    feedback_tasks: list[dict[str, Any]] | None = None,
    feedback_passed: int = 0,
    server_error: bool = False,
    server_error_message: str | None = None,
    cooldown_seconds: int | None = None,
    cooldown_message: str | None = None,
    error_banner: str | None = None,
    processing: bool = False,
) -> dict[str, Any]:
    """Build the template context for ``partials/requirement_card.html``.

    Centralises context-building so the phase page and the HTMX submit
    route (including the SSE stream) all produce identically-shaped dicts.
    Pre-computes ``derived_url`` for read-only display and ``pr_url_prefix``
    for PR-review inputs so the Jinja template never builds URLs.

    Args:
        requirement: The :class:`HandsOnRequirement` being rendered.
            Must not be ``None`` — callers should handle missing
            requirements before calling this function.
        github_username: The authenticated learner's GitHub username, used
            to derive canonical URLs.  ``None`` when the user is not
            linked to GitHub.
        submission: The latest :class:`SubmissionData` for this requirement
            (or ``None``).
        feedback_tasks: Pre-built task-feedback entries.
        feedback_passed: Count of passing tasks (for the summary line).
        server_error: Whether to render the server-error banner.
        server_error_message: Optional server-error text.
        cooldown_seconds: Optional remaining cooldown seconds.
        cooldown_message: Optional cooldown banner text.
        error_banner: Optional inline error banner text.
        processing: Whether the card is in the LLM "analysing..." state.
    """
    derived_url: str | None = None
    pr_url_prefix: str | None = None

    if requirement is not None and github_username:
        sub_type = requirement.submission_type
        try:
            if is_derivable(sub_type):
                derived_url = derive_submission_value(
                    requirement=requirement,
                    github_username=github_username,
                    user_input=None,
                )
            elif (
                sub_type == SubmissionType.PR_REVIEW
                and requirement.required_repo
                and "/" in requirement.required_repo
            ):
                fork = fork_name_from_required_repo(requirement.required_repo)
                pr_url_prefix = f"https://github.com/{github_username}/{fork}/pull/"
        except ValueError:
            # Misconfigured requirement (e.g. missing required_repo).  The
            # template will fall back to its read-only placeholder branch.
            derived_url = None
            pr_url_prefix = None

    return {
        "requirement": requirement,
        "submission": submission,
        "feedback_tasks": feedback_tasks or [],
        "feedback_passed": feedback_passed,
        "server_error": server_error,
        "server_error_message": server_error_message,
        "cooldown_seconds": cooldown_seconds,
        "cooldown_message": cooldown_message,
        "error_banner": error_banner,
        "processing": processing,
        "derived_url": derived_url,
        "pr_url_prefix": pr_url_prefix,
    }


def build_topic_nav(
    topics: list[Topic],
    current_slug: str,
    phase_id: int,
    phase_name: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Build prev/next navigation links for a topic page.

    Returns:
        ``(prev_topic, next_topic)`` — each is a dict with ``slug``,
        ``name``, and ``url`` keys, or ``None`` if at the boundary.
    """
    current_idx = next((i for i, t in enumerate(topics) if t.slug == current_slug), -1)
    if current_idx == -1:
        return None, None

    phase_link = {
        "slug": None,
        "name": phase_name,
        "url": f"/phase/{phase_id}",
    }

    # Previous
    if current_idx == 0:
        prev_topic = phase_link
    else:
        prev_t = topics[current_idx - 1]
        prev_topic = {
            "slug": prev_t.slug,
            "name": prev_t.name,
            "url": f"/phase/{phase_id}/{prev_t.slug}",
        }

    # Next
    if current_idx == len(topics) - 1:
        next_topic = phase_link
    else:
        next_t = topics[current_idx + 1]
        next_topic = {
            "slug": next_t.slug,
            "name": next_t.name,
            "url": f"/phase/{phase_id}/{next_t.slug}",
        }

    return prev_topic, next_topic
