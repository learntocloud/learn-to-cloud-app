"""Progress and feedback rendering helpers for route handlers.

Centralises the data-shaping that routes perform before passing
context to Jinja2 templates. Keeps route functions thin and
avoids duplicated dict-building logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote, urlparse

from learn_to_cloud_shared.schemas import (
    CareerReflectionRequirement,
    CtfTokenRequirement,
    DeployedApiRequirement,
    HandsOnRequirement,
    NetworkingTokenRequirement,
    SubmissionData,
)
from learn_to_cloud_shared.submission_derivation import (
    derive_submission_value,
    is_derivable,
)

from learn_to_cloud.verification_forms import (
    MAX_REFLECTION_ANSWER_LENGTH,
    DeployedUrlFormContext,
    DerivedFormContext,
    ReflectionFormContext,
    TokenFormContext,
    UnsupportedFormContext,
    VerificationFormContext,
    verification_submit_action,
)

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import (
        Phase,
        PhaseProgress,
        Topic,
    )

DISCUSSIONS_URL = "https://github.com/learntocloud/learn-to-cloud-app/discussions"
DISCORD_URL = "https://discord.gg/st7g2Hp77r"
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

_DISCORD_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor"'
    ' aria-hidden="true"><path d="M19.54 5.34A16.3 16.3 0 0 0 15.44'
    " 4l-.5 1.02a15.3 15.3 0 0 0-5.88 0L8.56 4a16.5 16.5 0 0 0"
    "-4.1 1.35C1.86 9.18 1.16 12.9 1.5 16.57A16.8 16.8 0 0 0"
    " 6.52 19.1l1.23-1.68c-.68-.25-1.33-.57-1.94-.94l.48-.37c3.74"
    " 1.73 7.8 1.73 11.5 0l.5.37c-.62.37-1.27.69-1.95.94l1.23"
    " 1.68a16.7 16.7 0 0 0 5.02-2.53c.4-4.26-.68-7.94-3.05"
    "-11.23ZM8.68 14.35c-1.12 0-2.04-1.03-2.04-2.3s.9-2.3"
    " 2.04-2.3c1.15 0 2.06 1.04 2.04 2.3 0 1.27-.9 2.3-2.04"
    " 2.3Zm6.64 0c-1.12 0-2.04-1.03-2.04-2.3s.9-2.3 2.04-2.3"
    'c1.15 0 2.06 1.04 2.04 2.3 0 1.27-.9 2.3-2.04 2.3Z"/></svg>'
)

COMMUNITY_LINKS: list[dict[str, str]] = [
    {
        "url": DISCORD_URL,
        "label": "Discord",
        "description": "Chat with other learners and get help in real time.",
        "color": "text-indigo-500 dark:text-indigo-400",
        "icon": _DISCORD_SVG,
    },
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
        "url": DISCORD_URL,
        "label": "Discord",
        "color": "text-indigo-500 dark:text-indigo-400",
        "icon": _DISCORD_SVG,
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
    "a problem on our side, not something you did. You can try again. If it keeps "
    "failing, report the issue."
)


@dataclass(frozen=True, slots=True)
class FeedbackEvidenceContext:
    """One safe evidence label with an optional repository link."""

    label: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackCriterionContext:
    """Learner-facing rubric criterion feedback."""

    id: str
    label: str
    kind: Literal["required", "quality", "bonus"]
    status: Literal["met", "not_met", "not_applicable"]
    explanation: str
    next_steps: str
    evidence: tuple[FeedbackEvidenceContext, ...]


@dataclass(frozen=True, slots=True)
class FeedbackTaskContext:
    """One deterministic task or structured rubric review."""

    name: str
    passed: bool
    message: str
    next_steps: str
    criteria: tuple[FeedbackCriterionContext, ...]


@dataclass(frozen=True, slots=True)
class _RequirementCardBase:
    """Fields shared by every requirement-card state."""

    requirement: HandsOnRequirement
    feedback_tasks: list[FeedbackTaskContext]
    feedback_passed: int

    @property
    def feedback_has_structured_criteria(self) -> bool:
        return any(task.criteria for task in self.feedback_tasks)

    @property
    def feedback_required_total(self) -> int:
        return sum(
            criterion.kind == "required"
            for task in self.feedback_tasks
            for criterion in task.criteria
        )

    @property
    def feedback_required_passed(self) -> int:
        return sum(
            criterion.kind == "required" and criterion.status == "met"
            for task in self.feedback_tasks
            for criterion in task.criteria
        )

    @property
    def feedback_required_unmet(self) -> int:
        return self.feedback_required_total - self.feedback_required_passed

    @property
    def feedback_suggestions(self) -> int:
        return sum(
            criterion.kind != "required" and criterion.status != "met"
            for task in self.feedback_tasks
            for criterion in task.criteria
        )


@dataclass(frozen=True, slots=True)
class NotStartedCardContext(_RequirementCardBase):
    """A submittable requirement with no completed attempt."""

    verification_form: VerificationFormContext
    error_message: str | None = None
    kind: Literal["not_started"] = field(init=False, default="not_started")


@dataclass(frozen=True, slots=True)
class CheckingCardContext(_RequirementCardBase):
    """An active verification attempt."""

    verification_status_token: str | None
    verification_status_delay_seconds: int
    kind: Literal["checking"] = field(init=False, default="checking")


@dataclass(frozen=True, slots=True)
class FailedCardContext(_RequirementCardBase):
    """A completed learner attempt that did not pass."""

    verification_form: VerificationFormContext
    error_message: str
    kind: Literal["failed"] = field(init=False, default="failed")


@dataclass(frozen=True, slots=True)
class UnavailableCardContext(_RequirementCardBase):
    """A verification-service failure."""

    verification_form: VerificationFormContext
    message: str
    kind: Literal["unavailable"] = field(init=False, default="unavailable")


@dataclass(frozen=True, slots=True)
class PassedCardContext(_RequirementCardBase):
    """A successfully verified requirement."""

    submission: SubmissionData
    graded_url: str | None
    kind: Literal["passed"] = field(init=False, default="passed")

    @property
    def graded_label(self) -> str | None:
        if not self.graded_url:
            return None
        parsed = urlparse(self.graded_url)
        if parsed.netloc == "github.com":
            return parsed.path.strip("/")
        return parsed.netloc or self.graded_url


type RequirementCardContext = (
    NotStartedCardContext
    | CheckingCardContext
    | FailedCardContext
    | UnavailableCardContext
    | PassedCardContext
)


def feedback_tasks_and_passed(
    feedback: dict[str, object] | None,
) -> tuple[list[FeedbackTaskContext], int]:
    """Extract ``(tasks, passed)`` from one ``feedback_by_req`` entry.

    ``PhaseSubmissionContext.feedback_by_req`` values are loosely typed
    (``dict[str, object]``) since they come straight off stored JSONB; this
    narrows them to what :func:`build_requirement_card_context` expects.
    """
    if not feedback:
        return [], 0
    raw_tasks = feedback.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return [], 0
    tasks = [
        FeedbackTaskContext(
            name=str(task.get("name", "")),
            passed=bool(task.get("passed", False)),
            message=str(task.get("message", "")),
            next_steps=str(task.get("next_steps", "")),
            criteria=tuple(
                _feedback_criterion(criterion)
                for criterion in criteria
                if isinstance(criterion, dict)
            ),
        )
        for task in raw_tasks
        if isinstance(task, dict)
        and isinstance((criteria := task.get("criteria", [])), list)
    ]
    passed_value = feedback.get("passed", 0)
    passed = passed_value if isinstance(passed_value, int) else 0
    return tasks, passed


def _feedback_criterion(raw: object) -> FeedbackCriterionContext:
    if not isinstance(raw, dict):
        raise TypeError("Feedback criterion must be an object")
    kind = raw.get("kind", "required")
    if kind not in {"required", "quality", "bonus"}:
        kind = "required"
    status = raw.get("status", "not_met")
    if status not in {"met", "not_met", "not_applicable"}:
        status = "not_met"
    raw_refs = raw.get("evidence_refs", [])
    refs = raw_refs if isinstance(raw_refs, list) else []
    return FeedbackCriterionContext(
        id=str(raw.get("id", "")),
        label=str(raw.get("label", "")),
        kind=kind,
        status=status,
        explanation=str(raw.get("explanation", "")),
        next_steps=str(raw.get("next_steps", "")),
        evidence=tuple(
            FeedbackEvidenceContext(label=str(reference)) for reference in refs
        ),
    )


_URL_SCHEMES = ("https://", "http://")


def _graded_url(submission: SubmissionData) -> str | None:
    """Return the graded value when it is a URL worth showing back.

    Token and free-text submissions are deliberately excluded: a career
    reflection can run to 20,000 characters and a completion token is noise,
    so neither belongs in the verified summary.
    """
    value = submission.submitted_value or ""
    return value if value.startswith(_URL_SCHEMES) else None


def _build_verification_form_context(
    requirement: HandsOnRequirement,
    github_username: str,
    submission: SubmissionData | None,
) -> VerificationFormContext:
    """Build exactly one valid rendering model for a requirement form."""
    action = verification_submit_action(
        requirement.slug,
        requirement.submission_type,
    )
    if action is None:
        return UnsupportedFormContext(
            message="Verification is not currently available for this requirement."
        )

    if is_derivable(requirement.submission_type):
        return DerivedFormContext(
            action=action,
            url=derive_submission_value(
                requirement=requirement,
                github_username=github_username,
            ).github_url,
        )

    if isinstance(requirement, CtfTokenRequirement | NetworkingTokenRequirement):
        return TokenFormContext(
            action=action,
            placeholder=(
                requirement.type_config.placeholder
                or "Paste your completion token here"
            ),
            min_length=requirement.type_config.min_length,
            max_length=requirement.type_config.max_length,
        )

    if isinstance(requirement, DeployedApiRequirement):
        return DeployedUrlFormContext(
            action=action,
            placeholder=(
                requirement.type_config.placeholder or "https://your-api.example.com"
            ),
            min_length=requirement.type_config.min_length,
            max_length=requirement.type_config.max_length,
            value=getattr(submission, "submitted_value", "") if submission else "",
        )

    if isinstance(requirement, CareerReflectionRequirement):
        return ReflectionFormContext(
            action=action,
            questions=tuple(requirement.type_config.questions),
            min_answer_length=requirement.type_config.min_answer_length,
            max_answer_length=MAX_REFLECTION_ANSWER_LENGTH,
        )

    raise ValueError(
        f"Submission type {requirement.submission_type.value!r} has an HTTP "
        "action but no rendering form model."
    )


def _card_feedback(
    feedback_tasks: list[FeedbackTaskContext] | None,
    feedback_passed: int,
    graded_url: str | None = None,
) -> tuple[list[FeedbackTaskContext], int]:
    tasks = feedback_tasks or []
    if graded_url:
        tasks = [_link_task_evidence(task, graded_url) for task in tasks]
    return tasks, feedback_passed


def _link_task_evidence(
    task: FeedbackTaskContext,
    repository_url: str,
) -> FeedbackTaskContext:
    return FeedbackTaskContext(
        name=task.name,
        passed=task.passed,
        message=task.message,
        next_steps=task.next_steps,
        criteria=tuple(
            FeedbackCriterionContext(
                id=criterion.id,
                label=criterion.label,
                kind=criterion.kind,
                status=criterion.status,
                explanation=criterion.explanation,
                next_steps=criterion.next_steps,
                evidence=tuple(
                    FeedbackEvidenceContext(
                        label=evidence.label,
                        url=_repository_evidence_url(
                            repository_url,
                            evidence.label,
                        ),
                    )
                    for evidence in criterion.evidence
                ),
            )
            for criterion in task.criteria
        ),
    )


def _repository_evidence_url(repository_url: str, reference: str) -> str | None:
    parsed = urlparse(repository_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or len(path_parts) != 2
        or not reference
        or any(character.isspace() for character in reference)
    ):
        return None
    evidence_path = PurePosixPath(reference)
    if evidence_path.is_absolute() or ".." in evidence_path.parts:
        return None
    return f"{repository_url.rstrip('/')}/blob/HEAD/{quote(reference, safe='/')}"


def build_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    github_username: str,
    submission: SubmissionData | None = None,
    feedback_tasks: list[FeedbackTaskContext] | None = None,
    feedback_passed: int = 0,
) -> RequirementCardContext:
    """Build a card state from the latest persisted submission."""
    graded_url = _graded_url(submission) if submission is not None else None
    tasks, passed = _card_feedback(feedback_tasks, feedback_passed, graded_url)
    if submission is not None and submission.is_validated:
        return PassedCardContext(
            requirement=requirement,
            feedback_tasks=tasks,
            feedback_passed=passed,
            submission=submission,
            graded_url=graded_url,
        )
    verification_form = _build_verification_form_context(
        requirement,
        github_username,
        submission,
    )
    if submission is None:
        return NotStartedCardContext(
            requirement=requirement,
            feedback_tasks=tasks,
            feedback_passed=passed,
            verification_form=verification_form,
        )
    if submission.verification_completed:
        return FailedCardContext(
            requirement=requirement,
            feedback_tasks=tasks,
            feedback_passed=passed,
            verification_form=verification_form,
            error_message=(
                submission.validation_message or "Verification did not pass."
            ),
        )
    return UnavailableCardContext(
        requirement=requirement,
        feedback_tasks=tasks,
        feedback_passed=passed,
        verification_form=verification_form,
        message=_PERSISTED_SERVICE_ERROR_MESSAGE,
    )


def build_checking_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    verification_status_token: str | None,
    verification_status_delay_seconds: int,
    feedback_tasks: list[FeedbackTaskContext] | None = None,
    feedback_passed: int = 0,
) -> CheckingCardContext:
    """Build the active-attempt card variant."""
    tasks, passed = _card_feedback(feedback_tasks, feedback_passed)
    return CheckingCardContext(
        requirement=requirement,
        feedback_tasks=tasks,
        feedback_passed=passed,
        verification_status_token=verification_status_token,
        verification_status_delay_seconds=verification_status_delay_seconds,
    )


def build_input_error_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    github_username: str,
    message: str,
) -> NotStartedCardContext:
    """Build a submittable card with a learner input error."""
    return NotStartedCardContext(
        requirement=requirement,
        feedback_tasks=[],
        feedback_passed=0,
        verification_form=_build_verification_form_context(
            requirement,
            github_username,
            None,
        ),
        error_message=message,
    )


def build_unavailable_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    github_username: str,
    message: str,
) -> UnavailableCardContext:
    """Build an explicit verification-service failure card."""
    return UnavailableCardContext(
        requirement=requirement,
        feedback_tasks=[],
        feedback_passed=0,
        verification_form=_build_verification_form_context(
            requirement,
            github_username,
            None,
        ),
        message=message,
    )


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
