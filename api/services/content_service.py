"""Content loading service.

This module loads course content from JSON files and provides
a clean interface for accessing phases and topics.

Content files are located in frontend/public/content/phases/ (dev) or
/app/content/phases/ (Docker) and are loaded once at startup for performance.
"""

import json
from functools import lru_cache
from pathlib import Path

from core.config import get_settings
from core.wide_event import set_wide_event_fields
from schemas import (
    LearningObjective,
    LearningStep,
    Phase,
    PhaseCapstoneOverview,
    PhaseHandsOnVerificationOverview,
    ProviderOption,
    Question,
    SecondaryLink,
    Topic,
)


def _get_content_dir() -> Path:
    """Get the content directory from settings.

    Lazily accessed to avoid module-level settings initialization.
    """
    return get_settings().content_dir_path


def _load_topic(phase_dir: Path, topic_slug: str) -> Topic | None:
    """Load a single topic from its JSON file."""
    topic_file = phase_dir / f"{topic_slug}.json"
    if not topic_file.exists():
        set_wide_event_fields(
            content_error="topic_not_found",
            content_topic_file=str(topic_file),
        )
        return None

    try:
        with open(topic_file, encoding="utf-8") as f:
            data = json.load(f)

        learning_steps = [
            LearningStep(
                order=s.get("order", i + 1),
                text=s.get("text", ""),
                action=s.get("action"),
                title=s.get("title"),
                url=s.get("url"),
                description=s.get("description"),
                code=s.get("code"),
                secondary_links=[
                    SecondaryLink(text=link["text"], url=link["url"])
                    for link in s.get("secondary_links", [])
                ],
                options=[
                    ProviderOption(
                        provider=opt["provider"],
                        title=opt["title"],
                        url=opt["url"],
                        description=opt.get("description"),
                    )
                    for opt in s.get("options", [])
                ],
            )
            for i, s in enumerate(data.get("learning_steps", []))
        ]

        from schemas import QuestionConcepts

        questions = [
            Question(
                id=q["id"],
                prompt=q["prompt"],
                scenario_seeds=q.get("scenario_seeds", []),
                grading_rubric=q.get("grading_rubric"),
                concepts=QuestionConcepts(**q["concepts"])
                if q.get("concepts")
                else None,
            )
            for q in data.get("questions", [])
        ]

        learning_objectives = [
            LearningObjective(
                id=obj.get("id", f"obj-{i}"),
                text=obj.get("text", ""),
                order=obj.get("order", i + 1),
            )
            for i, obj in enumerate(data.get("learning_objectives", []))
        ]

        return Topic(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            description=data.get("description", ""),
            order=data.get("order", 0),
            is_capstone=data.get("is_capstone", False),
            learning_steps=learning_steps,
            questions=questions,
            learning_objectives=learning_objectives,
        )
    except (json.JSONDecodeError, KeyError) as e:
        set_wide_event_fields(
            content_error="topic_load_failed",
            content_topic_slug=topic_slug,
            content_error_detail=str(e),
        )
        return None


def _load_phase(phase_slug: str) -> Phase | None:
    """Load a single phase from its directory."""
    phase_dir = _get_content_dir() / phase_slug
    index_file = phase_dir / "index.json"

    if not index_file.exists():
        set_wide_event_fields(
            content_error="phase_index_not_found",
            content_index_file=str(index_file),
        )
        return None

    try:
        with open(index_file, encoding="utf-8") as f:
            data = json.load(f)

        topic_slugs = list(data.get("topics", []))

        capstone: PhaseCapstoneOverview | None = None
        capstone_data = data.get("capstone")
        if isinstance(capstone_data, dict):
            capstone = PhaseCapstoneOverview(
                title=str(capstone_data.get("title", "")).strip(),
                summary=str(capstone_data.get("summary", "")).strip(),
                includes=list(capstone_data.get("includes", []) or []),
                topic_slug=capstone_data.get("topic_slug"),
            )

        hands_on_verification: PhaseHandsOnVerificationOverview | None = None
        hov_data = data.get("hands_on_verification")
        if isinstance(hov_data, dict):
            hands_on_verification = PhaseHandsOnVerificationOverview(
                summary=str(hov_data.get("summary", "")).strip(),
                includes=list(hov_data.get("includes", []) or []),
            )

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
            order=data.get("order", data["id"]),
            objectives=list(data.get("objectives", [])),
            capstone=capstone,
            hands_on_verification=hands_on_verification,
            topic_slugs=topic_slugs,
            topics=topics,
        )
    except (json.JSONDecodeError, KeyError) as e:
        set_wide_event_fields(
            content_error="phase_load_failed",
            content_phase_slug=phase_slug,
            content_error_detail=str(e),
        )
        return None


@lru_cache(maxsize=1)
def get_all_phases() -> tuple[Phase, ...]:
    """Get all phases in order.

    Results are cached for performance.
    Dynamically discovers phase directories (phase0, phase1, etc.).
    """
    phases = []
    content_dir = _get_content_dir()
    if not content_dir.exists():
        set_wide_event_fields(
            content_error="content_dir_not_found",
            content_dir=str(content_dir),
        )
        return ()

    for phase_dir in sorted(content_dir.iterdir()):
        if phase_dir.is_dir() and phase_dir.name.startswith("phase"):
            phase = _load_phase(phase_dir.name)
            if phase:
                phases.append(phase)

    if not phases:
        set_wide_event_fields(
            content_error="no_phases_loaded",
            content_dir=str(content_dir),
        )

    return tuple(sorted(phases, key=lambda p: p.order))


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


def clear_cache() -> None:
    """Clear the content cache (useful for testing)."""
    get_all_phases.cache_clear()
