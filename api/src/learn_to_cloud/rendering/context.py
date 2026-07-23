"""Progress and feedback rendering helpers for route handlers.

Centralises the data-shaping that routes perform before passing
context to Jinja2 templates. Keeps route functions thin and
avoids duplicated dict-building logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from learn_to_cloud_shared.submission_derivation import (
    derive_submission_value,
    is_derivable,
)

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import (
        Phase,
        PhaseProgress,
        Topic,
    )

DISCUSSIONS_URL = "https://github.com/learntocloud/learn-to-cloud-app/discussions"
GITHUB_REPOSITORY_URL = "https://github.com/learntocloud/learn-to-cloud-app"
MADEBYGPS_X_URL = "https://x.com/madebygps"
LEARN_TO_CLOUD_X_URL = "https://x.com/learntocloud"
YOUTUBE_URL = "https://youtube.com/made-by-gps"

# ── FAQ content ──────────────────────────────────────────────
# Stored here (rendering layer) rather than in templates or routes.
# Each entry is (question, answer_html).

_SPONSOR_LINK = (
    '<a href="https://github.com/sponsors/madebygps" target="_blank"'
    ' rel="noopener noreferrer"'
    ' class="text-blue-600 dark:text-blue-400 underline">sponsor us on GitHub</a>'
)
_DISCUSSIONS_LINK = (
    f'<a href="{DISCUSSIONS_URL}"'
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
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor"'
    ' aria-hidden="true">'
    '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817'
    "L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52"
    'h1.833L7.084 4.126H5.117z"/></svg>'
)

_DISCUSSIONS_SVG = (
    '<svg class="h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none"'
    ' viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"'
    ' aria-hidden="true">'
    '<path stroke-linecap="round" stroke-linejoin="round"'
    ' d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 0 1-2-2V6'
    "a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-4l-3 3-3-3z"
    '"/></svg>'
)

_GITHUB_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 16 16" fill="currentColor"'
    ' aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54'
    " 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38"
    " 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94"
    "-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53"
    ".63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66"
    ".07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95"
    " 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12"
    " 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27"
    ".68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82"
    ".44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15"
    " 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48"
    " 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38"
    "A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
    '"/></svg>'
)

_YOUTUBE_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor"'
    ' aria-hidden="true"><path d="M23.498 6.186a3.016 3.016 0 0 0'
    "-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0"
    "-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12"
    " 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136"
    "c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505"
    "a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12"
    " 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818"
    ' 12l-6.273 3.568z"/></svg>'
)

COMMUNITY_LINKS: list[dict[str, str]] = [
    {
        "url": DISCUSSIONS_URL,
        "label": "GitHub Discussions",
        "description": "Ask questions and connect with other learners.",
        "color": "text-indigo-500 dark:text-indigo-400",
        "icon": _DISCUSSIONS_SVG,
    },
    {
        "url": YOUTUBE_URL,
        "label": "YouTube",
        "description": "Watch cloud learning videos and project walkthroughs.",
        "color": "text-red-600 dark:text-red-400",
        "icon": _YOUTUBE_SVG,
    },
    {
        "url": GITHUB_REPOSITORY_URL,
        "label": "GitHub",
        "description": "Explore the project, contribute, or report a problem.",
        "color": "text-gray-800 dark:text-gray-200",
        "icon": _GITHUB_SVG,
    },
    {
        "url": MADEBYGPS_X_URL,
        "label": "Follow @madebygps",
        "description": "Follow the creator of Learn to Cloud.",
        "color": "text-gray-800 dark:text-gray-200",
        "icon": _X_SVG,
    },
    {
        "url": LEARN_TO_CLOUD_X_URL,
        "label": "Follow @learntocloud",
        "description": "Get project news and community updates.",
        "color": "text-gray-800 dark:text-gray-200",
        "icon": _X_SVG,
    },
]

HELP_LINKS: list[dict[str, str]] = [
    {
        "url": DISCUSSIONS_URL,
        "label": "Ask the Community",
        "color": "text-indigo-500 dark:text-indigo-400",
        "icon": _DISCUSSIONS_SVG,
    },
    {
        "url": MADEBYGPS_X_URL,
        "label": "Follow @madebygps",
        "color": "text-gray-800 dark:text-gray-200",
        "icon": _X_SVG,
    },
    {
        "url": LEARN_TO_CLOUD_X_URL,
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


def build_phase_topics(phase: Phase, detail: PhaseProgress) -> list[dict[str, Any]]:
    """Build template-ready topic list for a phase page.

    Merges topic metadata from content with per-topic learning progress.
    The phase's own learning/verification progress renders straight from
    ``detail`` (a typed ``PhaseProgress``) rather than a re-shaped dict --
    see ``pages/phase.html``.

    Returns:
        A list of dicts with ``name``, ``slug``, and ``progress`` keys.
    """
    topics: list[dict[str, Any]] = []
    for t in phase.topics:
        tp = detail.topic_progress.get(t.uuid) if detail.topic_progress else None
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

    return topics


_PERSISTED_SERVICE_ERROR_MESSAGE = (
    "The verification service couldn't finish checking this attempt because of "
    "a problem on our side, not something you did."
)


def _derive_card_state(
    submission: Any,
    *,
    processing: bool,
    server_error: bool,
) -> str:
    """Derive the one verification-card state that drives the whole card.

    Replaces the old combination of ``submission.is_validated`` /
    ``verification_completed`` / ``processing`` / ``server_error`` flags
    with a single state: ``checking``, ``passed``, ``failed`` (a real
    learner attempt that didn't pass), ``unavailable`` (a system/retryable
    fault -- covers both ``server_error`` and ``cancelled`` outcomes, since
    neither counts against the learner), or ``not_started``.
    """
    if processing:
        return "checking"
    if server_error:
        return "unavailable"
    if submission is None:
        return "not_started"
    if submission.is_validated:
        return "passed"
    if submission.verification_completed:
        return "failed"
    # Not validated and verification never completed -- a terminal
    # server_error/cancelled outcome read back from storage, not an
    # explicit override from the live submit/poll flow.
    return "unavailable"


def feedback_tasks_and_passed(
    feedback: dict[str, object] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Extract ``(tasks, passed)`` from one ``feedback_by_req`` entry.

    ``PhaseSubmissionContext.feedback_by_req`` values are loosely typed
    (``dict[str, object]``) since they come straight off stored JSONB; this
    narrows them to what :func:`build_requirement_card_context` expects.
    """
    if not feedback:
        return [], 0
    tasks = cast("list[dict[str, Any]]", feedback.get("tasks", []))
    passed = cast(int, feedback.get("passed", 0))
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
    server_error_retryable: bool = True,
    error_banner: str | None = None,
    processing: bool = False,
    verification_status_token: str | None = None,
    verification_status_delay_seconds: int = 2,
) -> dict[str, Any]:
    """Build the template context for ``partials/requirement_card.html``.

    Centralises context-building so the phase page and the HTMX submit/poll
    routes all produce identically-shaped dicts, and so a single
    ``card_state`` (see :func:`_derive_card_state`) -- not a scattered
    combination of flags -- drives which part of the card renders.
    Pre-computes ``derived_url`` for read-only display so the Jinja template
    never builds URLs.

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
        server_error: Whether to force the "service unavailable" state --
            used by the live submit/poll flow for a failure that has no
            ``submission`` row to derive from (e.g. Durable never started).
        server_error_message: Optional server-error text; defaults to a
            generic message when the state is derived from a persisted
            ``unavailable`` submission rather than passed explicitly.
        server_error_retryable: Whether to invite the user to retry. False for
            server-side problems (e.g. misconfiguration) where retrying cannot
            succeed, so the banner omits the "try again immediately" guidance.
        error_banner: Optional inline error banner text (e.g. a pre-submit
            validation message). Defaults to ``submission.validation_message``
            when the card state is ``failed`` and no override is given.
        processing: Whether the card is in the "analysing..." state.
        verification_status_token: Signed token used by the HTMX polling card.
        verification_status_delay_seconds: Delay before the next status poll.
    """
    derived_url: str | None = None
    if requirement is not None and github_username:
        try:
            if is_derivable(requirement.submission_type):
                derived_url = derive_submission_value(
                    requirement=requirement,
                    github_username=github_username,
                    user_input=None,
                )
        except ValueError:
            # Misconfigured requirement (e.g. missing required_repo).  The
            # template will fall back to its read-only placeholder branch.
            derived_url = None

    card_state = _derive_card_state(
        submission, processing=processing, server_error=server_error
    )
    if card_state == "unavailable":
        server_error = True
        if server_error_message is None:
            server_error_message = _PERSISTED_SERVICE_ERROR_MESSAGE
    elif card_state == "failed" and error_banner is None and submission is not None:
        error_banner = submission.validation_message

    return {
        "requirement": requirement,
        "submission": submission,
        "feedback_tasks": feedback_tasks or [],
        "feedback_passed": feedback_passed,
        "card_state": card_state,
        "server_error": server_error,
        "server_error_message": server_error_message,
        "server_error_retryable": server_error_retryable,
        "error_banner": error_banner,
        "processing": processing,
        "verification_status_token": verification_status_token,
        "verification_status_delay_seconds": verification_status_delay_seconds,
        "derived_url": derived_url,
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
