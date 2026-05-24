"""Content loading service.

This module loads course content from YAML files and provides
a clean interface for accessing phases and topics.

Content files are packaged with learn_to_cloud_shared and loaded once at startup
for performance.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.schemas import (
    HandsOnRequirementAdapter,
    Phase,
    Topic,
)

logger = logging.getLogger(__name__)


class ContentValidationError(Exception):
    """Raised when content YAML fails structural validation."""


def _validate_topic_payload(data: dict, topic_file: Path) -> None:
    """Validate topic payload learning step IDs are explicit and unique."""
    topic_id = str(data.get("id", "")).strip()
    topic_name = topic_id or topic_file.stem
    steps = data.get("learning_steps", [])
    if not isinstance(steps, list):
        raise ContentValidationError("learning_steps must be a list")

    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            raise ContentValidationError("Each learning step must be a mapping")

        step_id = str(step.get("id", "")).strip()
        if not step_id:
            raise ContentValidationError(
                f"Missing learning_steps[].id in topic '{topic_name}'"
            )
        if len(step_id) > 100:
            raise ContentValidationError(
                f"learning_steps[].id '{step_id[:60]}...' is {len(step_id)} chars "
                f"(max 100) in topic '{topic_name}'"
            )
        if step_id in seen:
            raise ContentValidationError(
                f"Duplicate learning_steps[].id '{step_id}' in topic '{topic_name}'"
            )
        seen.add(step_id)


def _get_content_dir() -> Path:
    """Get the content directory from settings.

    Lazily accessed to avoid module-level settings initialization.
    """
    return get_worker_settings().content_dir_path


def _load_topic(phase_dir: Path, topic_slug: str) -> Topic | None:
    """Load a single topic from its YAML file."""
    topic_file = phase_dir / f"{topic_slug}.yaml"
    if not topic_file.exists():
        return None

    try:
        with open(topic_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _validate_topic_payload(data, topic_file)
        return Topic.model_validate(data)
    except (yaml.YAMLError, ContentValidationError, ValueError, KeyError):
        logger.exception(
            "content.topic.load_failed",
            extra={
                "topic_slug": topic_slug,
                "path": str(topic_file),
            },
        )
        return None


def _load_requirement(phase_dir: Path, requirement_slug: str) -> Any | None:
    """Load a single hands-on requirement from its YAML file.

    Returns one of the typed ``HandsOnRequirement`` subclasses (resolved
    via the discriminated union) or ``None`` if the file is missing or
    fails validation.
    """
    req_file = phase_dir / "requirements" / f"{requirement_slug}.yaml"
    if not req_file.exists():
        return None

    try:
        with open(req_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ContentValidationError(
                f"requirement {req_file.name} must be a YAML mapping"
            )
        file_stem = req_file.stem
        yaml_id = str(data.get("id", "")).strip()
        if yaml_id != file_stem:
            raise ContentValidationError(
                f"requirement {req_file.name}: id '{yaml_id}' does not match "
                f"filename stem '{file_stem}'"
            )
        return HandsOnRequirementAdapter.validate_python(data)
    except (
        yaml.YAMLError,
        ContentValidationError,
        ValidationError,
        ValueError,
        KeyError,
    ):
        logger.exception(
            "content.requirement.load_failed",
            extra={
                "requirement_slug": requirement_slug,
                "path": str(req_file),
            },
        )
        return None


def _load_phase(phase_slug: str) -> Phase | None:
    """Load a single phase from its directory."""
    phase_dir = _get_content_dir() / phase_slug
    meta_file = phase_dir / "_phase.yaml"

    if not meta_file.exists():
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

        # ``hands_on_verification.requirements`` is a list of slug strings in
        # YAML; resolve each to a ``HandsOnRequirement`` loaded from
        # ``phase<N>/requirements/<slug>.yaml``.
        hov = data.get("hands_on_verification")
        if isinstance(hov, dict):
            requirement_slugs: list[str] = hov.get("requirements", []) or []
            if not all(isinstance(s, str) for s in requirement_slugs):
                raise ContentValidationError(
                    f"phase '{phase_slug}' hands_on_verification.requirements "
                    "must be a list of slug strings"
                )
            loaded_requirements = [
                r
                for slug in requirement_slugs
                if (r := _load_requirement(phase_dir, slug)) is not None
            ]
            hov["requirement_slugs"] = requirement_slugs
            hov["requirements"] = loaded_requirements

        return Phase.model_validate(data)
    except (yaml.YAMLError, ContentValidationError, ValueError, KeyError):
        logger.exception(
            "content.phase.load_failed",
            extra={
                "phase_slug": phase_slug,
                "path": str(meta_file),
            },
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
        return ()

    for phase_dir in sorted(content_dir.iterdir()):
        if phase_dir.is_dir() and phase_dir.name.startswith("phase"):
            phase = _load_phase(phase_dir.name)
            if phase:
                phases.append(phase)

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


# ---------------------------------------------------------------------------
# Cross-file validators (issue #462)
#
# get_all_phases() is intentionally tolerant -- it logs and skips broken
# files so the app keeps running on partially-bad content. The validators
# below are STRICT: they raise on the first violation. They are intended
# for CI and for the sync step that writes YAML into the DB.
# ---------------------------------------------------------------------------


def _collect_uuids(phases: tuple[Phase, ...]) -> list[tuple[str, str]]:
    """Return (uuid_str, locator) tuples for every curriculum entity.

    Locator is a human-readable path like ``phases[0]`` or
    ``topics[phase0-topic5].learning_steps[s1]`` so duplicates can be
    pointed at concretely.
    """
    items: list[tuple[str, str]] = []
    for phase in phases:
        items.append((str(phase.uuid), f"phase[{phase.slug}]"))
        if phase.hands_on_verification:
            for req in phase.hands_on_verification.requirements:
                items.append(
                    (
                        str(req.uuid),
                        f"phase[{phase.slug}].requirements[{req.id}]",
                    )
                )
        for topic in phase.topics:
            items.append((str(topic.uuid), f"topic[{topic.slug}]"))
            for obj in topic.learning_objectives:
                items.append(
                    (
                        str(obj.uuid),
                        f"topic[{topic.slug}].objectives[{obj.id}]",
                    )
                )
            for step in topic.learning_steps:
                items.append((str(step.uuid), f"topic[{topic.slug}].steps[{step.id}]"))
    return items


def _check_uuid_uniqueness(phases: tuple[Phase, ...]) -> list[str]:
    """Return error messages for any duplicate UUIDs."""
    by_uuid: dict[str, list[str]] = {}
    for uuid_str, locator in _collect_uuids(phases):
        by_uuid.setdefault(uuid_str, []).append(locator)

    errors: list[str] = []
    for uuid_str, locators in by_uuid.items():
        if len(locators) > 1:
            errors.append(f"Duplicate uuid {uuid_str} used by: {', '.join(locators)}")
    return errors


def _check_topic_slugs_resolve(phases: tuple[Phase, ...]) -> list[str]:
    """Return error messages for topic_slugs in phase yaml without a topic file.

    Compares counts: the loader silently drops topics whose files fail to
    parse, so a length mismatch between ``phase.topic_slugs`` (the YAML
    list of expected topic filenames) and ``phase.topics`` (successfully
    loaded ``Topic`` objects) means at least one slug did not load.
    """
    errors: list[str] = []
    for phase in phases:
        if len(phase.topics) < len(phase.topic_slugs):
            loaded_ids = {t.id for t in phase.topics}
            errors.append(
                f"phase[{phase.slug}] expected {len(phase.topic_slugs)} "
                f"topics but only {len(phase.topics)} loaded. "
                f"Listed topics: {phase.topic_slugs}. "
                f"Loaded topic ids: {sorted(loaded_ids)}. "
                "Check for YAML parse errors in the missing files."
            )
    return errors


def _check_step_order_uniqueness(phases: tuple[Phase, ...]) -> list[str]:
    """Return error messages for steps that share an order within a topic."""
    errors: list[str] = []
    for phase in phases:
        for topic in phase.topics:
            by_order: dict[int, list[str]] = {}
            for step in topic.learning_steps:
                by_order.setdefault(step.order, []).append(step.id)
            for order, step_ids in by_order.items():
                if len(step_ids) > 1:
                    errors.append(
                        f"topic[{topic.slug}] has multiple steps with "
                        f"order={order}: {', '.join(step_ids)}"
                    )
    return errors


def _check_requirement_slugs_resolve(phases: tuple[Phase, ...]) -> list[str]:
    """Return errors for requirement slugs in phase yaml without a loaded file.

    Same pattern as ``_check_topic_slugs_resolve``: counts of declared
    vs loaded must match; missing means a per-phase requirement file
    failed to parse.
    """
    errors: list[str] = []
    for phase in phases:
        if phase.hands_on_verification is None:
            continue
        declared = phase.hands_on_verification.requirement_slugs
        loaded = phase.hands_on_verification.requirements
        if len(loaded) < len(declared):
            loaded_ids = {r.id for r in loaded}
            errors.append(
                f"phase[{phase.slug}] expected {len(declared)} requirements "
                f"but only {len(loaded)} loaded. "
                f"Listed: {declared}. Loaded ids: {sorted(loaded_ids)}. "
                "Check for YAML parse errors in the missing requirement files."
            )
    return errors


def _check_requirement_ids_globally_unique(
    phases: tuple[Phase, ...],
) -> list[str]:
    """Return errors for requirement IDs that collide across the whole curriculum.

    Requirement IDs are used as filenames and as form field values.
    Two requirements sharing an ID would clash in lookup and break UI.
    """
    by_id: dict[str, list[str]] = {}
    for phase in phases:
        if phase.hands_on_verification is None:
            continue
        for req in phase.hands_on_verification.requirements:
            by_id.setdefault(req.id, []).append(phase.slug)

    errors: list[str] = []
    for req_id, phase_slugs in by_id.items():
        if len(phase_slugs) > 1:
            errors.append(
                f"Duplicate requirement id '{req_id}' appears in phases: "
                f"{', '.join(phase_slugs)}"
            )
    return errors


def validate_content() -> list[str]:
    """Run all cross-file validators against the currently-loaded content.

    Returns a list of error messages; empty list means no issues.
    Does not raise -- callers (CI scripts, sync step) decide how to handle
    the result.
    """
    phases = get_all_phases()
    errors: list[str] = []
    errors.extend(_check_uuid_uniqueness(phases))
    errors.extend(_check_topic_slugs_resolve(phases))
    errors.extend(_check_step_order_uniqueness(phases))
    errors.extend(_check_requirement_slugs_resolve(phases))
    errors.extend(_check_requirement_ids_globally_unique(phases))
    return errors
