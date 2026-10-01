"""Curriculum content models: phases, topics, and learning steps."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from learn_to_cloud.schemas.base import FrozenModel
from learn_to_cloud.schemas.requirements import HandsOnRequirement


class StepAction(StrEnum):
    """Categorical action label for a learning step.

    Drives the action label in the step UI. Authored in YAML as
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


def _normalize_step_action(raw: str) -> StepAction | None:
    """Normalize a YAML action label, returning None for an empty string."""
    cleaned = raw.strip().rstrip(":").strip().lower()
    if not cleaned:
        return None
    try:
        return StepAction(cleaned)
    except ValueError as exc:
        allowed = ", ".join(a.value for a in StepAction)
        raise ValueError(f"Unknown step action {raw!r}; allowed: {allowed}") from exc


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


class PhaseHandsOnVerificationOverview(FrozenModel):
    """High-level hands-on verification overview for a phase (public summary)."""

    # Raw slug list from ``_phase.yaml`` (each resolves to
    # ``phase<N>/requirements/<slug>.yaml``). Preserved alongside the
    # resolved ``requirements`` list so cross-file validators can detect
    # a count mismatch (a slug whose file failed to load).
    requirement_slugs: list[str] = Field(default_factory=list)
    requirements: list[HandsOnRequirement] = Field(default_factory=list)


class TimeEstimate(FrozenModel):
    """A deliberately broad estimate for self-paced curriculum work."""

    minimum_hours: float = Field(ge=0)
    maximum_hours: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.maximum_hours < self.minimum_hours:
            raise ValueError(
                "maximum_hours must be greater than or equal to minimum_hours"
            )
        return self


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
    estimated_learning_time: TimeEstimate = Field(
        default_factory=lambda: TimeEstimate(minimum_hours=0, maximum_hours=0)
    )
    estimated_project_time: TimeEstimate = Field(
        default_factory=lambda: TimeEstimate(minimum_hours=0, maximum_hours=0)
    )
    project_summary: str = ""
    completion_summary: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    cost_note: str = ""
    required_for_graduation: bool = True
    hands_on_verification: PhaseHandsOnVerificationOverview | None = None
    topic_slugs: list[str] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)


class TopicOverview(FrozenModel):
    """Browse-level topic summary: name only, no steps/objectives."""

    slug: str
    name: str


class PhaseOverview(FrozenModel):
    """Browse-level phase summary for home/curriculum listing pages.

    No topics-with-steps, no requirements: only what those pages render.
    """

    order: int
    name: str
    slug: str
    description: str = ""
    short_description: str = ""
    estimated_learning_time: TimeEstimate = Field(
        default_factory=lambda: TimeEstimate(minimum_hours=0, maximum_hours=0)
    )
    estimated_project_time: TimeEstimate = Field(
        default_factory=lambda: TimeEstimate(minimum_hours=0, maximum_hours=0)
    )
    project_summary: str = ""
    completion_summary: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    cost_note: str = ""
    required_for_graduation: bool = True
    topics: list[TopicOverview] = Field(default_factory=list)
