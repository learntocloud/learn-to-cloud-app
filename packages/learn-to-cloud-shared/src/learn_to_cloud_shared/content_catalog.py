"""Curriculum catalog: process-level reader of the compiled artifact.

Loads the packaged ``curriculum.json`` artifact (see
``content_compiler.py``) once per process and builds indexed lookups
over it (by UUID, by slug, by phase). This is the production reader for
request-serving curriculum reads (see ``content_service``); it exists so
the API can fail fast at startup if the packaged artifact is missing,
stale, or corrupted, and so callers never touch the database just to
read curriculum shape.

The PostgreSQL curriculum tables (populated by ``content_sync.py`` at
deploy time) and ``content_db_loader.py`` remain in place as a
compatibility shadow, but no request path reads them anymore.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from uuid import UUID

from learn_to_cloud_shared.content_compiler import (
    ARTIFACT_SCHEMA_VERSION,
    compute_content_hash,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    LearningStep,
    Phase,
    Topic,
)

#: Package-relative location of the compiled artifact, as passed to
#: ``importlib.resources.files(...).joinpath(*ARTIFACT_PACKAGE_PATH)``.
ARTIFACT_PACKAGE_PATH = ("content", "curriculum.json")

#: Shared empty sentinel for Mapping-typed dataclass field defaults.
_EMPTY_MAPPING: Mapping = MappingProxyType({})


class CurriculumCatalogError(Exception):
    """Raised when the packaged curriculum artifact can't be loaded or trusted."""


@dataclass(frozen=True, slots=True)
class CurriculumCatalog:
    """Immutable, indexed view over the compiled curriculum artifact.

    Build once per process via :func:`get_curriculum_catalog`. Lookup
    fields are ``Mapping``/``frozenset``/``tuple`` -- backed by
    ``MappingProxyType`` so item assignment raises ``TypeError``, not
    just plain dicts that happen to be typed as read-only. Values are
    the same Pydantic model instances found in ``phases``.
    """

    artifact_schema_version: int
    curriculum_version: int
    content_hash: str
    phases: tuple[Phase, ...]

    phases_by_slug: Mapping[str, Phase] = field(default_factory=lambda: _EMPTY_MAPPING)
    phases_by_order: Mapping[int, Phase] = field(default_factory=lambda: _EMPTY_MAPPING)
    topics_by_uuid: Mapping[UUID, Topic] = field(default_factory=lambda: _EMPTY_MAPPING)
    topics_by_phase_and_slug: Mapping[tuple[str, str], Topic] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    steps_by_uuid: Mapping[UUID, LearningStep] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    steps_by_phase_slug: Mapping[str, tuple[LearningStep, ...]] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    #: Resolves a step UUID straight to its owning topic (with sibling
    #: steps), so callers don't walk every topic to find the one that
    #: contains a given step.
    topic_by_step_uuid: Mapping[UUID, Topic] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    #: Resolves a step UUID straight to its owning phase's order, so
    #: per-user progress aggregation can group learner-state UUIDs by
    #: phase without a curriculum-table join.
    phase_order_by_step_uuid: Mapping[UUID, int] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    requirements_by_uuid: Mapping[UUID, HandsOnRequirement] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    requirements_by_slug: Mapping[str, HandsOnRequirement] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    requirements_by_phase_slug: Mapping[str, tuple[HandsOnRequirement, ...]] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    #: Resolves a requirement UUID straight to its owning phase's order,
    #: the cross-user stats mirror of ``phase_order_by_step_uuid``.
    phase_order_by_requirement_uuid: Mapping[UUID, int] = field(
        default_factory=lambda: _EMPTY_MAPPING
    )
    active_phase_uuids: frozenset[UUID] = field(default_factory=frozenset)
    active_topic_uuids: frozenset[UUID] = field(default_factory=frozenset)
    active_step_uuids: frozenset[UUID] = field(default_factory=frozenset)
    active_requirement_uuids: frozenset[UUID] = field(default_factory=frozenset)

    @property
    def phase_count(self) -> int:
        return len(self.phases)

    @property
    def topic_count(self) -> int:
        return len(self.topics_by_uuid)

    @property
    def step_count(self) -> int:
        return len(self.steps_by_uuid)

    @property
    def requirement_count(self) -> int:
        return len(self.requirements_by_uuid)

    @classmethod
    def from_phases(
        cls,
        phases: tuple[Phase, ...],
        *,
        artifact_schema_version: int,
        curriculum_version: int,
        content_hash: str,
    ) -> CurriculumCatalog:
        """Build every index in a single pass over the phase tree."""
        phases_by_slug: dict[str, Phase] = {}
        phases_by_order: dict[int, Phase] = {}
        topics_by_uuid: dict[UUID, Topic] = {}
        topics_by_phase_and_slug: dict[tuple[str, str], Topic] = {}
        steps_by_uuid: dict[UUID, LearningStep] = {}
        steps_by_phase_slug: dict[str, list[LearningStep]] = {}
        topic_by_step_uuid: dict[UUID, Topic] = {}
        phase_order_by_step_uuid: dict[UUID, int] = {}
        requirements_by_uuid: dict[UUID, HandsOnRequirement] = {}
        requirements_by_slug: dict[str, HandsOnRequirement] = {}
        requirements_by_phase_slug: dict[str, list[HandsOnRequirement]] = {}
        phase_order_by_requirement_uuid: dict[UUID, int] = {}

        for phase in phases:
            phases_by_slug[phase.slug] = phase
            phases_by_order[phase.order] = phase
            steps_by_phase_slug.setdefault(phase.slug, [])
            requirements_by_phase_slug.setdefault(phase.slug, [])

            for topic in phase.topics:
                topics_by_uuid[topic.uuid] = topic
                topics_by_phase_and_slug[(phase.slug, topic.slug)] = topic
                for step in topic.learning_steps:
                    steps_by_uuid[step.uuid] = step
                    steps_by_phase_slug[phase.slug].append(step)
                    topic_by_step_uuid[step.uuid] = topic
                    phase_order_by_step_uuid[step.uuid] = phase.order

            if phase.hands_on_verification:
                for req in phase.hands_on_verification.requirements:
                    requirements_by_uuid[req.uuid] = req
                    requirements_by_slug[req.slug] = req
                    requirements_by_phase_slug[phase.slug].append(req)
                    phase_order_by_requirement_uuid[req.uuid] = phase.order

        return cls(
            artifact_schema_version=artifact_schema_version,
            curriculum_version=curriculum_version,
            content_hash=content_hash,
            phases=phases,
            phases_by_slug=MappingProxyType(phases_by_slug),
            phases_by_order=MappingProxyType(phases_by_order),
            topics_by_uuid=MappingProxyType(topics_by_uuid),
            topics_by_phase_and_slug=MappingProxyType(topics_by_phase_and_slug),
            steps_by_uuid=MappingProxyType(steps_by_uuid),
            steps_by_phase_slug=MappingProxyType(
                {slug: tuple(steps) for slug, steps in steps_by_phase_slug.items()}
            ),
            topic_by_step_uuid=MappingProxyType(topic_by_step_uuid),
            phase_order_by_step_uuid=MappingProxyType(phase_order_by_step_uuid),
            requirements_by_uuid=MappingProxyType(requirements_by_uuid),
            requirements_by_slug=MappingProxyType(requirements_by_slug),
            requirements_by_phase_slug=MappingProxyType(
                {slug: tuple(reqs) for slug, reqs in requirements_by_phase_slug.items()}
            ),
            phase_order_by_requirement_uuid=MappingProxyType(
                phase_order_by_requirement_uuid
            ),
            active_phase_uuids=frozenset(p.uuid for p in phases),
            active_topic_uuids=frozenset(topics_by_uuid),
            active_step_uuids=frozenset(steps_by_uuid),
            active_requirement_uuids=frozenset(requirements_by_uuid),
        )


def _read_artifact_payload() -> dict:
    """Read and JSON-parse the packaged artifact, without validating it."""
    resource = files("learn_to_cloud_shared").joinpath(*ARTIFACT_PACKAGE_PATH)
    if not resource.is_file():
        raise CurriculumCatalogError(
            f"packaged curriculum artifact not found: {resource}. Run "
            "'uv run python scripts/compile_curriculum.py' in "
            "packages/learn-to-cloud-shared and commit the result."
        )

    raw = resource.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CurriculumCatalogError(
            f"packaged curriculum artifact is not valid JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise CurriculumCatalogError(
            "packaged curriculum artifact must be a JSON object"
        )
    return payload


def _validate_artifact_payload(payload: dict) -> None:
    """Fail fast on a schema mismatch or a corrupted/hand-edited artifact."""
    schema_version = payload.get("artifact_schema_version")
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise CurriculumCatalogError(
            f"packaged curriculum artifact schema_version {schema_version!r} does "
            f"not match the version this code expects ({ARTIFACT_SCHEMA_VERSION}); "
            "recompile with a matching learn-to-cloud-shared release."
        )

    content_hash = payload.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash:
        raise CurriculumCatalogError(
            "packaged curriculum artifact is missing content_hash"
        )

    payload_without_hash = {k: v for k, v in payload.items() if k != "content_hash"}
    expected_hash = compute_content_hash(payload_without_hash)
    if content_hash != expected_hash:
        raise CurriculumCatalogError(
            "packaged curriculum artifact content_hash does not match its "
            "payload -- the file may be corrupted or hand-edited"
        )


def load_curriculum_catalog() -> CurriculumCatalog:
    """Load, validate, and index the packaged curriculum artifact.

    Not cached -- call :func:`get_curriculum_catalog` for the
    process-level singleton. Exposed separately so tests can exercise
    fresh loads without touching the shared cache.
    """
    payload = _read_artifact_payload()
    _validate_artifact_payload(payload)

    phases = tuple(Phase.model_validate(p) for p in payload["phases"])
    return CurriculumCatalog.from_phases(
        phases,
        artifact_schema_version=payload["artifact_schema_version"],
        curriculum_version=payload["curriculum_version"],
        content_hash=payload["content_hash"],
    )


@lru_cache(maxsize=1)
def get_curriculum_catalog() -> CurriculumCatalog:
    """Get the process-level curriculum catalog singleton.

    Loaded once per process. Call this eagerly during API startup so a
    missing/stale/corrupted artifact fails the deploy instead of the
    first request that happens to need it.
    """
    return load_curriculum_catalog()


def clear_catalog_cache() -> None:
    """Clear the cached catalog singleton (useful for testing)."""
    get_curriculum_catalog.cache_clear()
