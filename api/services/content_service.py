"""Content loading service.

This module loads course content from YAML files and provides
a clean interface for accessing phases and topics.

Content files are located in content/phases/ (dev) or
/app/content/phases/ (Docker) and are loaded once at startup for performance.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from core.config import get_settings
from core.wide_event import set_wide_event_fields
from schemas import Phase, Topic


def _get_content_dir() -> Path:
    """Get the content directory from settings.

    Lazily accessed to avoid module-level settings initialization.
    """
    return get_settings().content_dir_path


def _load_topic(phase_dir: Path, topic_slug: str) -> Topic | None:
    """Load a single topic from its YAML file."""
    topic_file = phase_dir / f"{topic_slug}.yaml"
    if not topic_file.exists():
        set_wide_event_fields(
            content_error="topic_not_found",
            content_topic_file=str(topic_file),
        )
        return None

    try:
        with open(topic_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return Topic.model_validate(data)
    except Exception as e:
        set_wide_event_fields(
            content_error="topic_load_failed",
            content_topic_slug=topic_slug,
            content_error_detail=str(e),
        )
        return None


def _load_phase(phase_slug: str) -> Phase | None:
    """Load a single phase from its directory."""
    phase_dir = _get_content_dir() / phase_slug
    meta_file = phase_dir / "_phase.yaml"

    if not meta_file.exists():
        set_wide_event_fields(
            content_error="phase_meta_not_found",
            content_meta_file=str(meta_file),
        )
        return None

    try:
        with open(meta_file, encoding="utf-8") as f:
            data: dict = yaml.safe_load(f)

        # "topics" in the YAML is a list of slug strings; resolve to Topic objects
        topic_slugs: list[str] = data.get("topics", [])
        topics = [
            t for slug in topic_slugs if (t := _load_topic(phase_dir, slug)) is not None
        ]
        data["topic_slugs"] = topic_slugs
        data["topics"] = topics

        # Inject phase_id into each hands-on requirement
        phase_id = data.get("id", 0)
        hov = data.get("hands_on_verification")
        if isinstance(hov, dict):
            for req in hov.get("requirements", []) or []:
                req.setdefault("phase_id", phase_id)

        return Phase.model_validate(data)
    except Exception as e:
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
    phases: list[Phase] = []
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
