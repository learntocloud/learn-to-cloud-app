"""Content loading service.

This module loads course content from JSON files and provides
a clean interface for accessing phases and topics.

Content files are located in frontend/public/content/phases/ (dev) or
/app/content/phases/ (Docker) and are loaded once at startup for performance.
"""

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Content directory - configurable via env var.
# Defaults to frontend's static assets for local dev.
_default_content_dir = (
    Path(__file__).parent.parent.parent / "frontend" / "public" / "content" / "phases"
)
CONTENT_DIR = Path(os.environ.get("CONTENT_DIR", str(_default_content_dir)))


@dataclass(frozen=True)
class SecondaryLink:
    """A secondary link in a learning step description."""

    text: str
    url: str


@dataclass(frozen=True)
class ProviderOption:
    """Cloud provider-specific option for a learning step."""

    provider: str  # "aws", "azure", "gcp"
    title: str
    url: str
    description: str | None = None


@dataclass(frozen=True)
class LearningStep:
    """A learning step within a topic."""

    order: int
    text: str
    action: str | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    code: str | None = None
    secondary_links: tuple[SecondaryLink, ...] = ()
    options: tuple[ProviderOption, ...] = ()


@dataclass(frozen=True)
class Question:
    """A knowledge check question."""

    id: str
    prompt: str
    expected_concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class LearningObjective:
    """A learning objective for a topic."""

    id: str
    text: str
    order: int


@dataclass(frozen=True)
class Topic:
    """A topic within a phase."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    estimated_time: str
    is_capstone: bool
    learning_steps: tuple[LearningStep, ...]
    questions: tuple[Question, ...]
    learning_objectives: tuple[LearningObjective, ...] = ()


@dataclass(frozen=True)
class PhaseCapstoneOverview:
    """High-level capstone overview for a phase (public summary)."""

    title: str
    summary: str
    includes: tuple[str, ...] = ()
    topic_slug: str | None = None


@dataclass(frozen=True)
class PhaseHandsOnVerificationOverview:
    """High-level hands-on verification overview for a phase (public summary)."""

    summary: str
    includes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Phase:
    """A phase in the curriculum."""

    id: int
    name: str
    slug: str
    description: str
    short_description: str
    estimated_weeks: str
    order: int
    objectives: tuple[str, ...]
    capstone: PhaseCapstoneOverview | None
    hands_on_verification: PhaseHandsOnVerificationOverview | None
    topic_slugs: tuple[str, ...]
    topics: tuple[Topic, ...]


def _load_topic(phase_dir: Path, topic_slug: str) -> Topic | None:
    """Load a single topic from its JSON file."""
    topic_file = phase_dir / f"{topic_slug}.json"
    if not topic_file.exists():
        logger.warning(f"Topic file not found: {topic_file}")
        return None

    try:
        with open(topic_file, encoding="utf-8") as f:
            data = json.load(f)

        learning_steps = tuple(
            LearningStep(
                order=s.get("order", i + 1),
                text=s.get("text", ""),
                action=s.get("action"),
                title=s.get("title"),
                url=s.get("url"),
                description=s.get("description"),
                code=s.get("code"),
                secondary_links=tuple(
                    SecondaryLink(text=link["text"], url=link["url"])
                    for link in s.get("secondary_links", [])
                ),
                options=tuple(
                    ProviderOption(
                        provider=opt["provider"],
                        title=opt["title"],
                        url=opt["url"],
                        description=opt.get("description"),
                    )
                    for opt in s.get("options", [])
                ),
            )
            for i, s in enumerate(data.get("learning_steps", []))
        )

        questions = tuple(
            Question(
                id=q["id"],
                prompt=q["prompt"],
                expected_concepts=tuple(q.get("expected_concepts", [])),
            )
            for q in data.get("questions", [])
        )

        learning_objectives = tuple(
            LearningObjective(
                id=obj.get("id", f"obj-{i}"),
                text=obj.get("text", ""),
                order=obj.get("order", i + 1),
            )
            for i, obj in enumerate(data.get("learning_objectives", []))
        )

        return Topic(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            description=data.get("description", ""),
            order=data.get("order", 0),
            estimated_time=data.get("estimated_time", ""),
            is_capstone=data.get("is_capstone", False),
            learning_steps=learning_steps,
            questions=questions,
            learning_objectives=learning_objectives,
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error loading topic {topic_slug}: {e}")
        return None


def _load_phase(phase_slug: str) -> Phase | None:
    """Load a single phase from its directory."""
    phase_dir = CONTENT_DIR / phase_slug
    index_file = phase_dir / "index.json"

    if not index_file.exists():
        logger.warning(f"Phase index not found: {index_file}")
        return None

    try:
        with open(index_file, encoding="utf-8") as f:
            data = json.load(f)

        topic_slugs = tuple(data.get("topics", []))

        capstone: PhaseCapstoneOverview | None = None
        capstone_data = data.get("capstone")
        if isinstance(capstone_data, dict):
            capstone = PhaseCapstoneOverview(
                title=str(capstone_data.get("title", "")).strip(),
                summary=str(capstone_data.get("summary", "")).strip(),
                includes=tuple(capstone_data.get("includes", []) or ()),
                topic_slug=capstone_data.get("topic_slug"),
            )

        hands_on_verification: PhaseHandsOnVerificationOverview | None = None
        hov_data = data.get("hands_on_verification")
        if isinstance(hov_data, dict):
            hands_on_verification = PhaseHandsOnVerificationOverview(
                summary=str(hov_data.get("summary", "")).strip(),
                includes=tuple(hov_data.get("includes", []) or ()),
            )

        # Load all topics for this phase
        topics = []
        for topic_slug in topic_slugs:
            topic = _load_topic(phase_dir, topic_slug)
            if topic:
                topics.append(topic)

        return Phase(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            description=data.get("description", ""),
            short_description=data.get("short_description", ""),
            estimated_weeks=data.get("estimated_weeks", ""),
            order=data.get("order", data["id"]),
            objectives=tuple(data.get("objectives", [])),
            capstone=capstone,
            hands_on_verification=hands_on_verification,
            topic_slugs=topic_slugs,
            topics=tuple(topics),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error loading phase {phase_slug}: {e}")
        return None


@lru_cache(maxsize=1)
def get_all_phases() -> tuple[Phase, ...]:
    """Get all phases in order.

    Results are cached for performance.
    """
    phases = []
    for i in range(7):  # Phases 0-6
        phase = _load_phase(f"phase{i}")
        if phase:
            phases.append(phase)
    return tuple(sorted(phases, key=lambda p: p.order))


def get_phase_by_id(phase_id: int) -> Phase | None:
    """Get a phase by its numeric ID."""
    for phase in get_all_phases():
        if phase.id == phase_id:
            return phase
    return None


def get_phase_by_slug(slug: str) -> Phase | None:
    """Get a phase by its slug."""
    for phase in get_all_phases():
        if phase.slug == slug:
            return phase
    return None


def get_topic_by_id(topic_id: str) -> Topic | None:
    """Get a topic by its ID (e.g., 'phase0-topic1')."""
    for phase in get_all_phases():
        for topic in phase.topics:
            if topic.id == topic_id:
                return topic
    return None


def get_topic_by_slugs(phase_slug: str, topic_slug: str) -> Topic | None:
    """Get a topic by phase and topic slugs."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None
    for topic in phase.topics:
        if topic.slug == topic_slug:
            return topic
    return None


def get_phase_for_topic(topic_id: str) -> Phase | None:
    """Get the phase that contains a topic."""
    for phase in get_all_phases():
        for topic in phase.topics:
            if topic.id == topic_id:
                return phase
    return None


def clear_cache() -> None:
    """Clear the content cache (useful for testing)."""
    get_all_phases.cache_clear()
