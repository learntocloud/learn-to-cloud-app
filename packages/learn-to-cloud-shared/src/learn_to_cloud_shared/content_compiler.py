"""Deterministic curriculum artifact compiler.

Compiles the authored curriculum YAML tree into a single canonical JSON
artifact (``curriculum.json``) that ships as package data with the
``learn-to-cloud-shared`` wheel. The compiler is strict: it fails on
missing, skipped, malformed, or inconsistent content instead of silently
tolerating it (unlike ``content_yaml_loader.get_all_phases_from_yaml``,
which is intentionally tolerant so the running app survives one bad
file).

The artifact is:

- **Canonical**: object keys are sorted, so key ordering never depends
  on dict insertion order or field-declaration order drifting. Array
  element order is left untouched -- it carries curriculum meaning
  (phase/topic/step order, requirement declaration order) that
  alphabetizing would destroy.
- **Deterministic**: compiling the same YAML twice produces
  byte-identical output. CI regenerates the artifact and diffs it
  against the committed copy to catch drift (see
  ``scripts/compile_curriculum.py``).
- **Versioned**: ``artifact_schema_version`` is the shape of this JSON
  artifact itself; ``curriculum_version`` is an authored integer bumped
  by curriculum maintainers in ``curriculum.meta.yaml`` -- it may repeat
  while content is unchanged, must never decrease, and must strictly
  increase whenever content changes (see ``_check_version_policy``);
  ``content_hash`` is a SHA-256 over the canonical payload (everything
  except the hash field itself), letting any consumer verify the
  artifact wasn't corrupted or hand-edited.

This module does not affect runtime curriculum reads -- those still go
through ``content_service`` (DB-backed). See ``content_catalog.py`` for
the process-level reader of the compiled artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from learn_to_cloud_shared.content_yaml_loader import (
    get_all_phases_from_yaml_strict,
    get_content_root_dir,
    validate_content,
)
from learn_to_cloud_shared.schemas import Phase

#: Shape of the compiled artifact. Bump when the top-level JSON structure
#: changes in a way that requires readers (CurriculumCatalog) to change.
ARTIFACT_SCHEMA_VERSION = 1

ARTIFACT_FILENAME = "curriculum.json"
META_FILENAME = "curriculum.meta.yaml"


class ContentCompileError(Exception):
    """Raised when the curriculum cannot be compiled into an artifact."""


def _read_curriculum_version(content_root: Path) -> int:
    """Read the authored version from ``curriculum.meta.yaml``."""
    meta_file = content_root / META_FILENAME
    if not meta_file.exists():
        raise ContentCompileError(f"missing curriculum metadata file: {meta_file}")

    with open(meta_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "curriculum_version" not in data:
        raise ContentCompileError(
            f"{meta_file} must define an integer 'curriculum_version'"
        )

    version = data["curriculum_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ContentCompileError(
            f"{meta_file}: curriculum_version must be a positive integer, "
            f"got {version!r}"
        )
    return version


def _content_without_version_and_hash(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip the two fields that don't count as "content" for version policy."""
    excluded = ("curriculum_version", "content_hash")
    return {k: v for k, v in payload.items() if k not in excluded}


def _check_version_policy(
    new_version: int,
    new_payload_without_hash: dict[str, Any],
    previous_path: Path,
) -> None:
    """Enforce the curriculum_version policy against a previous artifact.

    - A missing previous artifact (first-ever compile) always passes.
    - A version decrease always fails.
    - An unchanged version is only allowed if the content (everything
      but ``curriculum_version``/``content_hash``) is unchanged too --
      a content change requires a strictly higher version.
    """
    if not previous_path.exists():
        return

    with open(previous_path, encoding="utf-8") as f:
        previous_payload = json.load(f)

    previous_version = previous_payload.get("curriculum_version")
    if not isinstance(previous_version, int):
        raise ContentCompileError(
            f"{previous_path}: previous artifact has no integer curriculum_version"
        )

    if new_version < previous_version:
        raise ContentCompileError(
            f"curriculum_version must not decrease: previous artifact has "
            f"{previous_version}, authored metadata has {new_version}."
        )

    if new_version == previous_version:
        previous_content = _content_without_version_and_hash(previous_payload)
        new_content = _content_without_version_and_hash(new_payload_without_hash)
        if previous_content != new_content:
            raise ContentCompileError(
                f"curriculum content changed but curriculum_version "
                f"({new_version}) was not bumped. Bump curriculum_version in "
                f"{META_FILENAME}."
            )


def canonical_json(payload: dict[str, Any]) -> str:
    """Serialize with sorted object keys for a stable, hashable form.

    Array element order is preserved as-is (it's meaningful curriculum
    ordering, not incidental). Shared by the compiler (to compute
    ``content_hash``) and the catalog (to verify it on load).
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_content_hash(payload_without_hash: dict[str, Any]) -> str:
    """SHA-256 over the canonical form of a payload excluding ``content_hash``."""
    canonical = canonical_json(payload_without_hash).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _build_payload(
    phases: tuple[Phase, ...], curriculum_version: int
) -> dict[str, Any]:
    """Build the artifact payload (without ``content_hash``) from loaded phases.

    Reuses the existing Pydantic schema types directly via
    ``model_dump`` rather than hand-building a parallel JSON shape, so
    the artifact can never drift from the validated curriculum types.
    None of these models carry timestamps or filesystem paths.
    """
    return {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "curriculum_version": curriculum_version,
        "phases": [phase.model_dump(mode="json") for phase in phases],
    }


def compile_curriculum_artifact(
    *, previous_artifact_path: Path | None = None
) -> dict[str, Any]:
    """Compile the authored YAML curriculum into a canonical artifact dict.

    Strict end to end: raises ``ContentCompileError`` (or propagates the
    underlying ``ContentValidationError``/``ValidationError``/
    ``yaml.YAMLError`` from the strict loader) on any missing file,
    malformed YAML, failed schema validation, or cross-file
    inconsistency (duplicate UUIDs, unresolved slugs, non-sequential
    phase order, ...).

    ``previous_artifact_path``, when given and it exists, is checked
    against the curriculum_version policy (see
    ``_check_version_policy``). This is opt-in (default: no check) so
    plain regeneration from an unchanged source tree -- what CI's
    drift-detection diff relies on -- stays idempotent.
    """
    content_root = get_content_root_dir()
    curriculum_version = _read_curriculum_version(content_root)

    phases = get_all_phases_from_yaml_strict()
    if not phases:
        raise ContentCompileError("no phases loaded from YAML; refusing to compile")

    errors = validate_content(phases)
    if errors:
        joined = "\n  - ".join(errors)
        raise ContentCompileError(f"curriculum validation failed:\n  - {joined}")

    payload_without_hash = _build_payload(phases, curriculum_version)

    if previous_artifact_path is not None:
        _check_version_policy(
            curriculum_version, payload_without_hash, previous_artifact_path
        )

    content_hash = compute_content_hash(payload_without_hash)

    return {**payload_without_hash, "content_hash": content_hash}


def render_artifact_file(payload: dict[str, Any]) -> str:
    """Render the compiled payload as commit-ready file contents.

    Pretty-printed (sorted keys, 2-space indent) for readable diffs,
    with a trailing newline. Deterministic given the same payload --
    this is what CI regenerates and byte-compares against the committed
    file.
    """
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def compile_and_write(
    output_path: Path | None = None, *, previous_artifact_path: Path | None = None
) -> Path:
    """Compile the curriculum and write the canonical artifact file to disk.

    Returns the path written. Used by ``scripts/compile_curriculum.py``
    (developer regeneration and the CI drift check). Pass
    ``previous_artifact_path`` to enforce the curriculum_version policy
    against a prior artifact; omitted by default so regenerating from
    an unchanged tree reproduces the same bytes.
    """
    content_root = get_content_root_dir()
    target = output_path or (content_root / ARTIFACT_FILENAME)
    payload = compile_curriculum_artifact(previous_artifact_path=previous_artifact_path)
    target.write_text(render_artifact_file(payload), encoding="utf-8")
    return target
