"""YAML-backed curriculum loader (authoring source of truth).

This module loads the curriculum tree from the authored YAML files. After
Phase C (issue #461), runtime reads in the API go through the DB loader in
``content_db_loader.py`` via the public ``content_service`` module. The YAML
loader is still authoritative for deploy-time YAML to DB sync
(``content_sync.py``) and for the strict cross-file validators run in CI.
Production migration jobs provide the YAML path through ``CONTENT__DIR``.

Do not import from this module in request-serving code paths. Use
``learn_to_cloud_shared.content_service`` (async, DB-backed) instead.
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
    """Validate topic payload learning step slugs are explicit and unique."""
    topic_name = topic_file.stem
    steps = data.get("learning_steps", [])
    if not isinstance(steps, list):
        raise ContentValidationError("learning_steps must be a list")

    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            raise ContentValidationError("Each learning step must be a mapping")

        step_slug = str(step.get("slug", "")).strip()
        if not step_slug:
            raise ContentValidationError(
                f"Missing learning_steps[].slug in topic '{topic_name}'"
            )
        if len(step_slug) > 100:
            raise ContentValidationError(
                f"learning_steps[].slug '{step_slug[:60]}...' is "
                f"{len(step_slug)} chars (max 100) in topic '{topic_name}'"
            )
        if step_slug in seen:
            raise ContentValidationError(
                f"Duplicate learning_steps[].slug '{step_slug}' in topic '{topic_name}'"
            )
        seen.add(step_slug)


def _get_content_dir() -> Path:
    """Get the content directory from settings.

    Lazily accessed to avoid module-level settings initialization.
    """
    return get_worker_settings().content.dir_path


def get_content_root_dir() -> Path:
    """Get the ``content/`` directory (parent of ``phases/``).

    Used by the deterministic artifact compiler to locate
    ``curriculum.meta.yaml`` and to write the compiled
    ``curriculum.json`` next to ``phases/`` and ``schemas/``.
    """
    return _get_content_dir().parent


def _build_topic(topic_file: Path, *, order: int) -> Topic:
    """Parse and validate one topic YAML file into a ``Topic``."""
    with open(topic_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict) and "order" in data:
        raise ContentValidationError(
            f"topic {topic_file.name}: 'order' field is no longer allowed. "
            "Topic order is derived from the position in _phase.yaml's "
            "'topics:' list -- remove the 'order' field from this file."
        )
    _validate_topic_payload(data, topic_file)
    data["order"] = order
    return Topic.model_validate(data)


def _load_topic(
    phase_dir: Path, topic_slug: str, *, order: int, strict: bool = False
) -> Topic | None:
    """Load a single topic from its YAML file.

    ``order`` is supplied by the caller from the topic's position in the
    parent phase's ``topics:`` slug list. Topic YAML files must not
    carry their own ``order`` field; the loader rejects it to keep one
    source of truth (issue #463).

    In tolerant mode (``strict=False``, the default), a missing file or
    any validation failure is logged and skipped so the app keeps
    running on partially-bad content. In strict mode (used by the
    deterministic artifact compiler), the same failures raise instead
    of being swallowed.
    """
    topic_file = phase_dir / f"{topic_slug}.yaml"
    if not topic_file.exists():
        if strict:
            raise ContentValidationError(f"missing topic file: {topic_file}")
        return None

    if strict:
        return _build_topic(topic_file, order=order)

    try:
        return _build_topic(topic_file, order=order)
    except (yaml.YAMLError, ContentValidationError, ValueError, KeyError):
        logger.exception(
            "content.topic.load_failed",
            extra={
                "topic_slug": topic_slug,
                "path": str(topic_file),
            },
        )
        return None


def _build_requirement(req_file: Path) -> Any:
    """Parse and validate one requirement YAML file into a typed requirement."""
    with open(req_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ContentValidationError(
            f"requirement {req_file.name} must be a YAML mapping"
        )
    file_stem = req_file.stem
    yaml_slug = str(data.get("slug", "")).strip()
    if yaml_slug != file_stem:
        raise ContentValidationError(
            f"requirement {req_file.name}: slug '{yaml_slug}' does not "
            f"match filename stem '{file_stem}'"
        )
    return HandsOnRequirementAdapter.validate_python(data)


def _load_requirement(
    phase_dir: Path, requirement_slug: str, *, strict: bool = False
) -> Any | None:
    """Load a single hands-on requirement from its YAML file.

    Returns one of the typed ``HandsOnRequirement`` subclasses (resolved
    via the discriminated union). In tolerant mode (the default),
    returns ``None`` if the file is missing or fails validation. In
    strict mode, the same conditions raise instead.
    """
    req_file = phase_dir / "requirements" / f"{requirement_slug}.yaml"
    if not req_file.exists():
        if strict:
            raise ContentValidationError(f"missing requirement file: {req_file}")
        return None

    if strict:
        return _build_requirement(req_file)

    try:
        return _build_requirement(req_file)
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


def _build_phase(
    phase_slug: str, phase_dir: Path, meta_file: Path, *, strict: bool
) -> Phase:
    """Parse and validate one phase directory into a ``Phase``."""
    with open(meta_file, encoding="utf-8") as f:
        data: dict = yaml.safe_load(f)

    # The phase directory name is authoritative -- the loader injects
    # the slug here rather than trusting any YAML field, so a file
    # accidentally placed in the wrong directory still ends up tagged
    # with that directory's slug.
    data["slug"] = phase_slug

    topic_slugs: list[str] = data.get("topics", [])
    topics = [
        t
        for idx, slug in enumerate(topic_slugs)
        if (t := _load_topic(phase_dir, slug, order=idx + 1, strict=strict)) is not None
    ]
    data["topic_slugs"] = topic_slugs
    data["topics"] = topics

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
            if (r := _load_requirement(phase_dir, slug, strict=strict)) is not None
        ]
        hov["requirement_slugs"] = requirement_slugs
        hov["requirements"] = loaded_requirements

    return Phase.model_validate(data)


def _load_phase(phase_slug: str, *, strict: bool = False) -> Phase | None:
    """Load a single phase from its directory.

    In tolerant mode (the default), a missing ``_phase.yaml`` or any
    validation failure (in this phase or any of its topics/requirements)
    is logged and skipped. In strict mode, the same failures raise.
    """
    phase_dir = _get_content_dir() / phase_slug
    meta_file = phase_dir / "_phase.yaml"

    if not meta_file.exists():
        if strict:
            raise ContentValidationError(f"missing phase metadata file: {meta_file}")
        return None

    if strict:
        return _build_phase(phase_slug, phase_dir, meta_file, strict=strict)

    try:
        return _build_phase(phase_slug, phase_dir, meta_file, strict=strict)
    except (yaml.YAMLError, ContentValidationError, ValueError, KeyError):
        logger.exception(
            "content.phase.load_failed",
            extra={
                "phase_slug": phase_slug,
                "path": str(meta_file),
            },
        )
        return None


def _discover_phases(*, strict: bool) -> tuple[Phase, ...]:
    """Load every phase directory under the content dir, in directory order."""
    phases: list[Phase] = []
    content_dir = _get_content_dir()
    if not content_dir.exists():
        if strict:
            raise ContentValidationError(
                f"content directory does not exist: {content_dir}"
            )
        return ()

    for phase_dir in sorted(content_dir.iterdir()):
        if phase_dir.is_dir() and phase_dir.name.startswith("phase"):
            phase = _load_phase(phase_dir.name, strict=strict)
            if phase:
                phases.append(phase)

    return tuple(sorted(phases, key=lambda p: p.order))


@lru_cache(maxsize=1)
def get_all_phases_from_yaml() -> tuple[Phase, ...]:
    """Get all phases in order from authored YAML files.

    Results are cached for performance. Dynamically discovers phase
    directories (phase0, phase1, ...). Tolerant of broken individual
    files (logs and skips) -- used by the API's process-level content
    cache. Used by ``content_sync.py`` (deploy-time YAML to DB sync) and
    by the strict cross-file validators invoked in CI.
    """
    return _discover_phases(strict=False)


def get_all_phases_from_yaml_strict() -> tuple[Phase, ...]:
    """Get all phases in order, raising on any missing/malformed content.

    Unlike ``get_all_phases_from_yaml``, this never silently skips a
    broken file -- every phase, topic, and requirement must parse and
    validate cleanly. Used by the deterministic curriculum artifact
    compiler, which must fail the build rather than emit a
    partially-populated artifact. Not cached: it's only invoked from a
    one-shot compile step.
    """
    return _discover_phases(strict=True)


def clear_cache() -> None:
    """Clear the YAML loader cache (useful for testing)."""
    get_all_phases_from_yaml.cache_clear()


# ---------------------------------------------------------------------------
# Cross-file validators (issue #462)
#
# get_all_phases_from_yaml() is intentionally tolerant -- it logs and skips
# broken files so the app keeps running on partially-bad content. The
# validators below are STRICT: they raise on the first violation. They are
# intended for CI and for the sync step that writes YAML into the DB.
# ---------------------------------------------------------------------------


def _collect_uuids(phases: tuple[Phase, ...]) -> list[tuple[str, str]]:
    """Return (uuid_str, locator) tuples for every curriculum entity."""
    items: list[tuple[str, str]] = []
    for phase in phases:
        items.append((str(phase.uuid), f"phase[{phase.slug}]"))
        if phase.hands_on_verification:
            for req in phase.hands_on_verification.requirements:
                items.append(
                    (
                        str(req.uuid),
                        f"phase[{phase.slug}].requirements[{req.slug}]",
                    )
                )
        for topic in phase.topics:
            items.append((str(topic.uuid), f"topic[{topic.slug}]"))
            for obj in topic.learning_objectives:
                items.append(
                    (
                        str(obj.uuid),
                        f"topic[{topic.slug}].objectives[{obj.uuid}]",
                    )
                )
            for step in topic.learning_steps:
                items.append(
                    (
                        str(step.uuid),
                        f"topic[{topic.slug}].steps[{step.slug}]",
                    )
                )
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
    """Return error messages for topic_slugs in phase yaml without a topic file."""
    errors: list[str] = []
    for phase in phases:
        if len(phase.topics) < len(phase.topic_slugs):
            loaded_slugs = {t.slug for t in phase.topics}
            errors.append(
                f"phase[{phase.slug}] expected {len(phase.topic_slugs)} "
                f"topics but only {len(phase.topics)} loaded. "
                f"Listed topics: {phase.topic_slugs}. "
                f"Loaded topic slugs: {sorted(loaded_slugs)}. "
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
                by_order.setdefault(step.order, []).append(step.slug)
            for order, step_slugs in by_order.items():
                if len(step_slugs) > 1:
                    errors.append(
                        f"topic[{topic.slug}] has multiple steps with "
                        f"order={order}: {', '.join(step_slugs)}"
                    )
    return errors


def _check_requirement_slugs_resolve(phases: tuple[Phase, ...]) -> list[str]:
    """Return errors for requirement slugs in phase yaml without a loaded file."""
    errors: list[str] = []
    for phase in phases:
        if phase.hands_on_verification is None:
            continue
        declared = phase.hands_on_verification.requirement_slugs
        loaded = phase.hands_on_verification.requirements
        if len(loaded) < len(declared):
            loaded_slugs = {r.slug for r in loaded}
            errors.append(
                f"phase[{phase.slug}] expected {len(declared)} requirements "
                f"but only {len(loaded)} loaded. "
                f"Listed: {declared}. Loaded slugs: {sorted(loaded_slugs)}. "
                "Check for YAML parse errors in the missing requirement files."
            )
    return errors


def _check_requirement_slugs_globally_unique(
    phases: tuple[Phase, ...],
) -> list[str]:
    """Return errors for requirement slugs that collide across the curriculum."""
    by_slug: dict[str, list[str]] = {}
    for phase in phases:
        if phase.hands_on_verification is None:
            continue
        for req in phase.hands_on_verification.requirements:
            by_slug.setdefault(req.slug, []).append(phase.slug)

    errors: list[str] = []
    for req_slug, phase_slugs in by_slug.items():
        if len(phase_slugs) > 1:
            errors.append(
                f"Duplicate requirement slug '{req_slug}' appears in phases: "
                f"{', '.join(phase_slugs)}"
            )
    return errors


def _check_phase_order_sequence(phases: tuple[Phase, ...]) -> list[str]:
    """Return errors unless phase orders form a gapless 0..N-1 sequence.

    Phase ``order`` is author-supplied in ``_phase.yaml`` (unlike topic
    and step order, it isn't derived from list position), so it can
    drift -- a duplicate or a gap would silently break the ``/phase/{order}``
    URL contract and phase navigation.
    """
    orders = sorted(phase.order for phase in phases)
    expected = list(range(len(phases)))
    if orders == expected:
        return []
    return [
        f"Phase orders must be a gapless 0..{len(phases) - 1} sequence with no "
        f"duplicates; found {orders}"
    ]


def validate_content(phases: tuple[Phase, ...] | None = None) -> list[str]:
    """Run all cross-file validators against the given (or YAML-loaded) content.

    Returns a list of error messages; empty list means no issues. Does
    not raise -- callers (CI scripts, the sync step, the artifact
    compiler) decide how to handle the result. Pass ``phases`` to
    validate an already-loaded (e.g. strictly-loaded) tree instead of
    re-reading the tolerant cached loader.
    """
    if phases is None:
        phases = get_all_phases_from_yaml()
    errors: list[str] = []
    errors.extend(_check_uuid_uniqueness(phases))
    errors.extend(_check_topic_slugs_resolve(phases))
    errors.extend(_check_step_order_uniqueness(phases))
    errors.extend(_check_requirement_slugs_resolve(phases))
    errors.extend(_check_requirement_slugs_globally_unique(phases))
    errors.extend(_check_phase_order_sequence(phases))
    return errors
