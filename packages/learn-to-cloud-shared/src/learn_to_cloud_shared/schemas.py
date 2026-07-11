"""Shared data types for API validation and cross-service payloads.

Holds the Pydantic models used for API request/response validation and
service-layer responses. Models use ``frozen=True`` for immutability where
appropriate.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, get_args
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    computed_field,
    field_validator,
)

from learn_to_cloud_shared.models import SubmissionType


class StepAction(StrEnum):
    """Categorical action label for a learning step.

    Drives the colored action badge in the step UI. Authored in YAML as
    ``action: 'Practice:'`` (capitalized, trailing colon) for readability;
    the schema validator normalizes to the lowercase enum value at load
    time. The trailing colon is purely a YAML-author affordance and
    never reaches the rendered UI.
    """

    BUILD = "build"
    EXPLORE = "explore"
    NOTE = "note"
    PRACTICE = "practice"
    READ = "read"
    REFLECT = "reflect"
    REVIEW = "review"
    WATCH = "watch"

    @property
    def label(self) -> str:
        """Display label shown inside the badge (e.g. ``Practice``)."""
        return self.value.capitalize()

    @property
    def badge_classes(self) -> str:
        """Tailwind utility classes for the action's colored pill."""
        return _ACTION_BADGE_CLASSES[self]


_ACTION_BADGE_CLASSES: dict[StepAction, str] = {
    StepAction.EXPLORE: (
        "bg-purple-100 text-purple-700 dark:bg-purple-800/40 dark:text-purple-300"
    ),
    StepAction.PRACTICE: (
        "bg-blue-100 text-blue-700 dark:bg-blue-800/40 dark:text-blue-300"
    ),
    StepAction.REFLECT: (
        "bg-amber-100 text-amber-700 dark:bg-amber-800/40 dark:text-amber-300"
    ),
    StepAction.BUILD: (
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-800/40 dark:text-emerald-300"
    ),
    StepAction.READ: ("bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"),
    StepAction.WATCH: ("bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"),
    StepAction.REVIEW: (
        "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
    ),
    StepAction.NOTE: ("bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"),
}


class TipType(StrEnum):
    """Categorical type for a callout/tip attached to a learning step."""

    TIP = "tip"
    NOTE = "note"
    WARNING = "warning"
    IMPORTANT = "important"

    @property
    def icon(self) -> str:
        return _TIP_ICONS[self]

    @property
    def container_classes(self) -> str:
        return _TIP_CONTAINER_CLASSES[self]

    @property
    def text_classes(self) -> str:
        return _TIP_TEXT_CLASSES[self]


_TIP_ICONS: dict[TipType, str] = {
    TipType.TIP: "\U0001f4a1",  # 💡
    TipType.NOTE: "\u2139\ufe0f",  # ℹ️
    TipType.WARNING: "\u26a0\ufe0f",  # ⚠️
    TipType.IMPORTANT: "\u2757",  # ❗
}

_TIP_CONTAINER_CLASSES: dict[TipType, str] = {
    TipType.TIP: (
        "bg-emerald-50 border border-emerald-200 "
        "dark:bg-emerald-900/20 dark:border-emerald-800/50"
    ),
    TipType.NOTE: (
        "bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800/50"
    ),
    TipType.WARNING: (
        "bg-amber-50 border border-amber-200 "
        "dark:bg-amber-900/20 dark:border-amber-800/50"
    ),
    TipType.IMPORTANT: (
        "bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800/50"
    ),
}

_TIP_TEXT_CLASSES: dict[TipType, str] = {
    TipType.TIP: "text-emerald-800 dark:text-emerald-200",
    TipType.NOTE: "text-blue-800 dark:text-blue-200",
    TipType.WARNING: "text-amber-800 dark:text-amber-200",
    TipType.IMPORTANT: "text-red-800 dark:text-red-200",
}


def _normalize_step_action(raw: str | StepAction | None) -> StepAction | None:
    """Accept YAML strings like ``"Practice:"`` and normalize to StepAction.

    Returns None for missing/empty values; raises ValueError for unknown
    labels so authoring mistakes (typos) fail at load time.
    """
    if raw is None:
        return None
    if isinstance(raw, StepAction):
        return raw
    cleaned = raw.strip().rstrip(":").strip().lower()
    if not cleaned:
        return None
    try:
        return StepAction(cleaned)
    except ValueError as exc:
        allowed = ", ".join(a.value for a in StepAction)
        raise ValueError(f"Unknown step action {raw!r}; allowed: {allowed}") from exc


class FrozenModel(BaseModel):
    """Base class for immutable Pydantic models (replaces frozen dataclasses)."""

    model_config = ConfigDict(frozen=True)


class StrictFrozenModel(BaseModel):
    """Immutable model that rejects unknown YAML fields.

    Use for curriculum entities so authoring mistakes (typos, stale
    fields) fail at load time instead of being silently ignored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class UserBase(BaseModel):
    """Base user schema."""

    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


class UserResponse(UserBase):
    """User response schema (also used as service-layer response model)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    is_admin: bool = False
    created_at: datetime


# ---------------------------------------------------------------------------
# Hands-on requirement type_config models (issue #470)
#
# Every requirement has the same top-level keys
# (uuid, id, submission_type, name, description, type_config).
# Variation between submission types lives inside ``type_config``.
# Pydantic validates per-type config via a discriminated union, so YAML
# authors get parse errors for mismatched fields (e.g., placeholder on a
# github_profile requirement).
# ---------------------------------------------------------------------------


class EmptyConfig(StrictFrozenModel):
    """No type-specific config (used by github_profile, profile_readme)."""


class RepoConfig(StrictFrozenModel):
    """Config shared by all GitHub-repo-backed verification types."""

    required_repo: str = Field(
        description="Upstream repo (owner/name) the learner forks from.",
    )


class PlaceholderConfig(StrictFrozenModel):
    """Config shared by free-form input verification types (tokens, URLs)."""

    placeholder: str | None = Field(
        default=None,
        description="Input hint shown in the form field.",
    )


# Per-type config classes inherit from the shared shape. Even when
# behavior is identical, having per-type names keeps JSON Schema clear
# and lets one type evolve fields independently in the future.


class RepoForkConfig(RepoConfig):
    """Config for repo_fork requirements."""


class JournalApiVerifierConfig(RepoConfig):
    """Config for journal_api_verifier requirements."""


class DevopsAnalysisConfig(RepoConfig):
    """Config for devops_analysis requirements."""


class SecurityScanningConfig(RepoConfig):
    """Config for security_scanning requirements."""


class CtfTokenConfig(PlaceholderConfig):
    """Config for ctf_token requirements."""


class NetworkingTokenConfig(PlaceholderConfig):
    """Config for networking_token requirements."""


class DeployedApiConfig(PlaceholderConfig):
    """Config for deployed_api requirements."""


class CareerReflectionQuestion(StrictFrozenModel):
    """One reflection prompt the learner answers in the app."""

    id: str = Field(description="Stable id for this question.")
    prompt: str = Field(description="The reflection prompt shown to the learner.")


class CareerReflectionConfig(StrictFrozenModel):
    """Config for career_reflection requirements."""

    questions: list[CareerReflectionQuestion] = Field(
        description="Reflection prompts the learner answers in the app.",
        min_length=1,
    )
    min_answer_length: int = Field(
        default=200,
        ge=1,
        description="Minimum characters required for each answer.",
    )


class DeploymentArchitectureConfig(RepoConfig):
    """Config for deployment_architecture requirements.

    The learner writes a free-text architecture description in the app; the
    grader fetches ``deploy_script_path`` from the learner's fork of
    ``required_repo`` and an LLM rubric checks the description against what the
    script actually provisions.
    """

    prompt: str = Field(
        description="The architecture-description prompt shown to the learner.",
    )
    min_answer_length: int = Field(
        default=200,
        ge=1,
        description="Minimum characters required for the description.",
    )
    deploy_script_path: str = Field(
        default="deploy.sh",
        description="Repo-relative path to the deployment script to grade.",
    )


# ---------------------------------------------------------------------------
# Hands-on requirement subclasses, one per active SubmissionType
# (issue #470)
# ---------------------------------------------------------------------------


class _RequirementBase(StrictFrozenModel):
    """Shared top-level fields for every hands-on requirement.

    Subclasses add a ``submission_type`` discriminator field and a typed
    ``type_config``.
    """

    uuid: UUID
    slug: str
    name: str
    description: str

    @property
    def placeholder(self) -> str | None:
        """Backwards-compat shim: read ``type_config.placeholder`` if any."""
        cfg = getattr(self, "type_config", None)
        return getattr(cfg, "placeholder", None) if cfg is not None else None


class GithubProfileRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.GITHUB_PROFILE]
    type_config: EmptyConfig = Field(default_factory=EmptyConfig)


class ProfileReadmeRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.PROFILE_README]
    type_config: EmptyConfig = Field(default_factory=EmptyConfig)


class RepoForkRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.REPO_FORK]
    type_config: RepoForkConfig


class CtfTokenRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.CTF_TOKEN]
    type_config: CtfTokenConfig = Field(default_factory=CtfTokenConfig)


class NetworkingTokenRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.NETWORKING_TOKEN]
    type_config: NetworkingTokenConfig = Field(default_factory=NetworkingTokenConfig)


class JournalApiVerifierRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.JOURNAL_API_VERIFIER]
    type_config: JournalApiVerifierConfig


class DeployedApiRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.DEPLOYED_API]
    type_config: DeployedApiConfig = Field(default_factory=DeployedApiConfig)


class DevopsAnalysisRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.DEVOPS_ANALYSIS]
    type_config: DevopsAnalysisConfig


class SecurityScanningRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.SECURITY_SCANNING]
    type_config: SecurityScanningConfig


class CareerReflectionRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.CAREER_REFLECTION]
    type_config: CareerReflectionConfig


class DeploymentArchitectureRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.DEPLOYMENT_ARCHITECTURE]
    type_config: DeploymentArchitectureConfig


HandsOnRequirement = Annotated[
    GithubProfileRequirement
    | ProfileReadmeRequirement
    | RepoForkRequirement
    | CtfTokenRequirement
    | NetworkingTokenRequirement
    | JournalApiVerifierRequirement
    | DeployedApiRequirement
    | DevopsAnalysisRequirement
    | SecurityScanningRequirement
    | CareerReflectionRequirement
    | DeploymentArchitectureRequirement,
    Field(discriminator="submission_type"),
]

# Annotated unions don't expose ``model_validate``; use this adapter for
# rehydrating requirements from JSON/dict payloads (e.g., durable
# verification jobs).
HandsOnRequirementAdapter = TypeAdapter(HandsOnRequirement)


# The submission types this code version can render, derived from the
# discriminated union's members so it can never drift from the union. Used by
# the content loader as a tolerant reader: during a rolling deploy the DB may
# already hold a newer submission_type this revision doesn't know, and those
# rows must be ignored rather than 500 the whole page.
def _known_submission_types() -> frozenset[str]:
    union = get_args(HandsOnRequirement)[0]
    tags: set[str] = set()
    for member in get_args(union):
        literal = get_args(member.model_fields["submission_type"].annotation)[0]
        tags.add(literal.value if isinstance(literal, SubmissionType) else str(literal))
    return frozenset(tags)


KNOWN_HANDS_ON_SUBMISSION_TYPES: frozenset[str] = _known_submission_types()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


class StepCompletionResult(FrozenModel):
    """Result of completing a step (service-layer response model)."""

    topic_slug: str
    step_slug: str
    completed_at: datetime


class ProviderOption(FrozenModel):
    """Cloud provider or platform-specific option for a learning step."""

    provider: str
    title: str
    url: str
    description: str | None = None


class TipItem(FrozenModel):
    """A tip, note, or warning callout for a learning step."""

    type: TipType = TipType.TIP
    text: str


class LearningStep(FrozenModel):
    """A learning step within a topic."""

    # Stable opaque identifier (issue #462).
    uuid: UUID
    slug: str
    order: int
    action: StepAction | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    code: str | None = None
    options: list[ProviderOption] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    tips: list[TipItem] = Field(default_factory=list)
    done_when: str | None = None

    @field_validator("action", mode="before")
    @classmethod
    def _normalize_action(cls, value: object) -> StepAction | None:
        if isinstance(value, StepAction) or value is None:
            return value
        if isinstance(value, str):
            return _normalize_step_action(value)
        raise TypeError(f"action must be a string or StepAction, got {type(value)}")

    @property
    def sorted_options(self) -> list[ProviderOption]:
        """Options sorted by canonical provider order (Azure, AWS, GCP, ...).

        Implemented as a plain ``@property`` rather than ``@computed_field``
        so the serialized payload doesn't grow a duplicate list. Lists
        are small (~3 items) so recomputing per render is negligible.
        """
        return sorted(self.options, key=_provider_sort_key)


def _provider_sort_key(option: ProviderOption) -> tuple[int, str]:
    """Canonical provider ordering: Azure → AWS → GCP → everything else."""
    key = (option.provider or "").strip().lower()
    if key == "azure":
        return (0, key)
    if key == "aws":
        return (1, key)
    if key == "gcp":
        return (2, key)
    return (3, key)


class LearningObjective(FrozenModel):
    """A learning objective for a topic."""

    # Stable opaque identifier (issue #462).
    uuid: UUID
    text: str
    order: int


class Topic(FrozenModel):
    """A topic within a phase.

    Display order is determined by the topic's position in the parent
    phase's ``topics:`` slug list (in ``_phase.yaml``); the loader
    injects ``order`` based on that position. Topic YAML files do not
    carry an ``order`` field -- two sources of truth would inevitably
    drift (issue #463).
    """

    # Stable opaque identifier (issue #462).
    uuid: UUID
    slug: str
    name: str
    description: str
    order: int
    learning_steps: list[LearningStep]
    learning_objectives: list[LearningObjective] = Field(default_factory=list)


class PhaseCapstoneOverview(FrozenModel):
    """High-level capstone overview for a phase (public summary)."""

    title: str
    summary: str
    includes: list[str] = Field(default_factory=list)
    topic_slug: str | None = None


class PhaseHandsOnVerificationOverview(FrozenModel):
    """High-level hands-on verification overview for a phase (public summary)."""

    # Raw slug list from ``_phase.yaml`` (each resolves to
    # ``phase<N>/requirements/<slug>.yaml``). Preserved alongside the
    # resolved ``requirements`` list so cross-file validators can detect
    # a count mismatch (a slug whose file failed to load).
    requirement_slugs: list[str] = Field(default_factory=list)
    requirements: list[HandsOnRequirement] = Field(default_factory=list)


class Phase(FrozenModel):
    """A phase in the curriculum.

    Phases use ``slug`` (e.g. ``"phase0"``) and ``order`` (int ``0..7``)
    as their human keys. The slug is what shows up in URLs and is the
    primary lookup key; ``order`` drives display ordering and is also
    used in URL paths today (``/phase/{order}``).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    # Stable opaque identifier (issue #462).
    uuid: UUID
    name: str
    slug: str
    description: str = ""
    short_description: str = ""
    order: int = 0
    objectives: list[str] = Field(default_factory=list)
    capstone: PhaseCapstoneOverview | None = None
    hands_on_verification: PhaseHandsOnVerificationOverview | None = None
    topic_slugs: list[str] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)


class TopicOverview(FrozenModel):
    """Browse-level topic summary: name only, no steps/objectives."""

    uuid: UUID
    slug: str
    name: str


class PhaseOverview(FrozenModel):
    """Browse-level phase summary for home/curriculum listing pages.

    No topics-with-steps, no requirements: only what those pages render.
    """

    uuid: UUID
    order: int
    name: str
    slug: str
    description: str = ""
    short_description: str = ""
    topics: list[TopicOverview] = Field(default_factory=list)


class TopicProgressData(FrozenModel):
    """Progress status for a topic (service-layer response model)."""

    steps_completed: int
    steps_total: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class PhaseProgressData(FrozenModel):
    """Progress status for a phase (service-layer response model)."""

    steps_completed: int
    steps_required: int
    hands_on_validated: int
    hands_on_required: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class PhaseSummaryData(FrozenModel):
    """Phase summary data for the dashboard (service-layer response model).

    Trimmed to exactly what ``dashboard.html`` renders: order, name,
    and progress. Full phase content (description, objectives,
    capstone, requirements) belongs to the phase detail view, not the
    dashboard list.
    """

    order: int
    name: str
    slug: str
    progress: PhaseProgressData | None = None


class ContinuePhaseData(FrozenModel):
    """Pointer to the user's current in-progress phase."""

    phase_id: int
    name: str
    slug: str
    order: int


class DashboardData(FrozenModel):
    """Complete dashboard payload (service-layer response model)."""

    phases: list[PhaseSummaryData]
    overall_percentage: float
    phases_completed: int
    total_phases: int
    is_program_complete: bool
    continue_phase: ContinuePhaseData | None = None


class CommunityMember(FrozenModel):
    """A learner shown publicly on the /stats page."""

    github_username: str
    avatar_url: str | None = None


class FunnelLevel(FrozenModel):
    """One level of the /stats progress funnel.

    ``pct_of_total`` is relative to total accounts (drives the funnel
    width); ``pct_of_previous`` is the conversion from the level above
    (``None`` for the top level).
    """

    label: str
    count: int
    pct_of_total: float
    pct_of_previous: float | None = None
    is_total: bool = False


class RepoUpdate(FrozenModel):
    """Latest commit for a curriculum repo (service-layer response model).

    ``available`` is False when the GitHub lookup failed (rate limit,
    network error); the page still renders the repo with a fallback.
    """

    name: str
    url: str
    available: bool = True
    commit_message: str | None = None
    commit_author: str | None = None
    commit_url: str | None = None
    committed_at: datetime | None = None


class StatsPageData(FrozenModel):
    """Complete /stats payload (service-layer response model)."""

    total_accounts: int
    funnel: list[FunnelLevel]
    graduates: list[CommunityMember]
    repo_updates: list[RepoUpdate]


class PhaseProgress(FrozenModel):
    """User's progress for a single phase.

    Unified model used by both dashboard and phase detail views.
    When topic_progress is populated, provides per-topic breakdown.
    """

    phase_id: int
    steps_completed: int
    steps_required: int
    hands_on_validated: int  # count of validated requirements
    hands_on_required: int  # count of required requirements
    topic_progress: dict[UUID, TopicProgressData] | None = None

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Phase is complete when all requirements are met."""
        return (
            self.steps_completed >= self.steps_required
            and self.hands_on_validated >= self.hands_on_required
        )

    @computed_field
    @property
    def status(self) -> str:
        """Phase status string."""
        if self.is_complete:
            return "completed"
        if self.steps_completed > 0 or self.hands_on_validated > 0:
            return "in_progress"
        return "not_started"

    @computed_field
    @property
    def percentage(self) -> float:
        """Phase completion percentage (steps + hands-on)."""
        total = self.steps_required + self.hands_on_required
        if total == 0:
            return 0.0
        completed = min(self.steps_completed, self.steps_required) + min(
            self.hands_on_validated, self.hands_on_required
        )
        return round((completed / total) * 100, 1)

    @computed_field
    @property
    def step_percentage(self) -> float:
        """Percentage of steps completed."""
        if self.steps_required == 0:
            return 100.0
        return round(min(100.0, (self.steps_completed / self.steps_required) * 100), 1)


class UserProgress(FrozenModel):
    """Complete progress summary for a user."""

    user_id: int
    phases: dict[int, PhaseProgress]
    total_phases: int

    @computed_field
    @property
    def phases_completed(self) -> int:
        """Count of fully completed phases."""
        return sum(1 for p in self.phases.values() if p.is_complete)

    @computed_field
    @property
    def current_phase(self) -> int:
        """First incomplete phase, or last phase if all done."""
        for phase_id in sorted(self.phases.keys()):
            if not self.phases[phase_id].is_complete:
                return phase_id
        return max(self.phases.keys()) if self.phases else 0

    @computed_field
    @property
    def is_program_complete(self) -> bool:
        """True if all phases are completed."""
        return self.phases_completed >= self.total_phases

    @computed_field
    @property
    def overall_percentage(self) -> float:
        """Overall completion percentage across all phases."""
        if not self.phases:
            return 0.0

        total_steps = sum(p.steps_required for p in self.phases.values())
        total_hands_on = sum(p.hands_on_required for p in self.phases.values())
        completed_steps = sum(p.steps_completed for p in self.phases.values())
        completed_hands_on = sum(p.hands_on_validated for p in self.phases.values())

        if total_steps + total_hands_on == 0:
            return 0.0

        total = total_steps + total_hands_on
        completed = min(completed_steps, total_steps) + min(
            completed_hands_on, total_hands_on
        )
        return round((completed / total) * 100, 1)


class SubmissionData(FrozenModel):
    """Submission data (service-layer response model).

    After Phase D.2 + D.3 of #461 / #465 the denormalized
    ``requirement_id`` / ``submission_type`` / ``phase_id`` columns
    are gone from the underlying ``submissions`` table and nothing
    in the app reads them off ``SubmissionData`` either -- callers
    that need them have the corresponding ``HandsOnRequirement``
    in scope.
    """

    id: int
    submitted_value: str
    extracted_username: str | None = None
    is_validated: bool
    validated_at: datetime | None = None
    verification_completed: bool = False
    feedback_json: list[dict] | None = None
    validation_message: str | None = None
    cloud_provider: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SubmissionResult(FrozenModel):
    """Result of a submission validation."""

    submission: SubmissionData
    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list["TaskResult"] | None = None

    @computed_field
    @property
    def is_server_error(self) -> bool:
        """Whether this failure was caused by a server-side error.

        True when validation failed but verification never completed
        (e.g. external service timeout). These attempts are
        not counted against the user's daily quota.
        """
        return not self.is_valid and not self.submission.verification_completed


class TaskResult(FrozenModel):
    """Result of verifying a single task in a multi-task verification.

    Used by DEVOPS_ANALYSIS and SECURITY_SCANNING validations to provide
    detailed per-task feedback.
    """

    task_name: str
    passed: bool
    feedback: str
    next_steps: str = ""


class PhaseSubmissionContext(FrozenModel):
    """Pre-built submission context for rendering a phase page."""

    submissions_by_req: dict[str, SubmissionData]
    feedback_by_req: dict[str, dict[str, object]]


class ValidationResult(FrozenModel):
    """Result of validating a hands-on submission.

    This is the common result type for ALL validation types.

    Attributes:
        is_valid: Whether the submission passed validation.
        message: User-facing message explaining the result.
        username_match: For GitHub-based validations, whether the submitted
            URL matches the authenticated user. None for non-GitHub validations.
        repo_exists: For GitHub-based validations, whether the repository
            exists. None for non-GitHub validations.
        task_results: For multi-task validations, detailed per-task feedback.
            None for single-check validations.
        verification_completed: False if validation failed due to a server-side
            issue (e.g., service unavailable, config error). When False, the
            attempt is not counted since the user isn't at fault.
        cloud_provider: Cloud provider for multi-cloud labs ("aws",
            "azure", "gcp"). None for non-multi-cloud validations.
    """

    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list[TaskResult] | None = None
    verification_completed: bool = True
    cloud_provider: str | None = None
