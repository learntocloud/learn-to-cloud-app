"""Hoist hands-on requirements out of inline phase YAML (one-time script).

Walks every ``phase<N>/_phase.yaml`` and, for each requirement object
inside ``hands_on_verification.requirements``:

1. Writes a new file ``phase<N>/requirements/<id>.yaml`` containing the
   requirement, restructured into uniform top-level keys
   (``uuid, id, submission_type, name, description, type_config``).
2. Replaces the inline requirement object in the phase file with just
   its ``id`` slug.

Idempotent: skips requirements that are already strings (already
hoisted). Refuses to overwrite an existing requirement file whose
contents differ from what we would write.

Uses ruamel.yaml in round-trip mode to preserve comments and key order
in the phase files.

Run from the package root::

    cd packages/learn-to-cloud-shared && \
        uv run python scripts/hoist_requirements_to_files.py

After committing the YAML changes, this script should not need to run
again. New requirements get authored directly as
``phase<N>/requirements/<id>.yaml`` files and referenced by slug in
``_phase.yaml``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

CONTENT_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "learn_to_cloud_shared"
    / "content"
    / "phases"
)

# Per-submission-type config field mapping. Keys are SubmissionType
# string values; values are lists of field names whose existence in the
# inline requirement should be moved into ``type_config``. Fields not
# listed are left at the top level of the new requirement file.
_TYPE_CONFIG_FIELDS: dict[str, list[str]] = {
    "profile_readme": [],
    "repo_fork": ["required_repo"],
    "ctf_token": ["placeholder"],
    "networking_token": ["placeholder"],
    "journal_api_verifier": ["required_repo"],
    "deployed_api": ["placeholder"],
    "devops_analysis": ["required_repo"],
    "security_scanning": ["required_repo"],
}

# Filename safety: kebab-case, alphanumeric and hyphen only.
_SAFE_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _is_safe_filename(slug: str) -> bool:
    return bool(_SAFE_FILENAME_RE.fullmatch(slug))


def _split_into_type_config(
    requirement: CommentedMap,
) -> tuple[CommentedMap, CommentedMap]:
    """Split a flat requirement mapping into (top-level, type_config).

    Top-level keeps: uuid, id, submission_type, name, description.
    type_config gets: whatever's in _TYPE_CONFIG_FIELDS for this type.
    Anything else stays at the top level (the script logs and refuses
    to lose data).
    """
    submission_type = str(requirement.get("submission_type", "")).strip()
    if submission_type not in _TYPE_CONFIG_FIELDS:
        raise ValueError(
            f"requirement id={requirement.get('id')!r} has unknown "
            f"submission_type={submission_type!r}; not in active set "
            f"({sorted(_TYPE_CONFIG_FIELDS)})"
        )

    config_fields = set(_TYPE_CONFIG_FIELDS[submission_type])
    top_level_fields = {"uuid", "id", "submission_type", "name", "description"}
    known_fields = top_level_fields | config_fields

    unknown = set(requirement.keys()) - known_fields
    if unknown:
        raise ValueError(
            f"requirement id={requirement.get('id')!r} has unexpected "
            f"fields {sorted(unknown)}; expected only "
            f"{sorted(known_fields)}"
        )

    new_top = CommentedMap()
    for key in ("uuid", "id", "submission_type", "name", "description"):
        if key in requirement:
            new_top[key] = requirement[key]

    new_type_config = CommentedMap()
    for key in _TYPE_CONFIG_FIELDS[submission_type]:
        if key in requirement:
            new_type_config[key] = requirement[key]

    return new_top, new_type_config


def _build_hoisted_requirement(requirement: CommentedMap) -> CommentedMap:
    """Produce the YAML doc for the new per-requirement file."""
    top, type_config = _split_into_type_config(requirement)
    if type_config:
        top["type_config"] = type_config
    return top


def _hoist_one_phase(phase_dir: Path, yaml: YAML) -> tuple[int, list[str]]:
    """Hoist all inline requirements in a single phase. Returns (count, warnings)."""
    phase_file = phase_dir / "_phase.yaml"
    with phase_file.open(encoding="utf-8") as f:
        doc = yaml.load(f)

    if not isinstance(doc, CommentedMap):
        return 0, [f"{phase_file} is not a YAML mapping"]

    hov = doc.get("hands_on_verification")
    if not isinstance(hov, CommentedMap):
        return 0, []

    raw_requirements = hov.get("requirements")
    if not isinstance(raw_requirements, CommentedSeq):
        return 0, []

    warnings: list[str] = []
    hoisted_count = 0
    new_slug_list = CommentedSeq()

    requirements_dir = phase_dir / "requirements"

    for item in raw_requirements:
        if isinstance(item, str):
            # Already hoisted; keep the slug reference as-is.
            new_slug_list.append(item)
            continue

        if not isinstance(item, CommentedMap):
            warnings.append(
                f"{phase_file}: requirement entry is neither a mapping nor a "
                f"slug string -- skipping"
            )
            continue

        req_id = str(item.get("id", "")).strip()
        if not req_id:
            warnings.append(f"{phase_file}: requirement missing id -- skipping")
            continue
        if not _is_safe_filename(req_id):
            raise ValueError(
                f"{phase_file}: requirement id {req_id!r} is not a safe "
                f"filename (kebab-case only)"
            )

        new_doc = _build_hoisted_requirement(item)
        out_path = requirements_dir / f"{req_id}.yaml"

        if out_path.exists():
            # Refuse to overwrite a conflicting file. Re-read and verify
            # it matches what we'd write; if so, it's idempotent and OK.
            with out_path.open(encoding="utf-8") as existing_f:
                existing_doc = yaml.load(existing_f)
            if existing_doc != new_doc:
                raise ValueError(
                    f"{out_path} already exists with different contents; "
                    f"refusing to overwrite"
                )
            # Same content -- treat as already hoisted, just collapse to slug.
            new_slug_list.append(req_id)
            continue

        requirements_dir.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as out_f:
            yaml.dump(new_doc, out_f)
        new_slug_list.append(req_id)
        hoisted_count += 1
        rel_out = out_path.relative_to(CONTENT_DIR.parent.parent.parent.parent)
        print(f"  hoisted {req_id} -> {rel_out}")

    if hoisted_count > 0:
        hov["requirements"] = new_slug_list
        with phase_file.open("w", encoding="utf-8") as f:
            yaml.dump(doc, f)
        rel_phase = phase_file.relative_to(CONTENT_DIR.parent.parent.parent.parent)
        print(f"  updated {rel_phase}")

    return hoisted_count, warnings


def main() -> int:
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}", file=sys.stderr)
        return 1

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096

    total_hoisted = 0
    all_warnings: list[str] = []

    for phase_dir in sorted(CONTENT_DIR.iterdir()):
        if not phase_dir.is_dir() or not phase_dir.name.startswith("phase"):
            continue
        count, warnings = _hoist_one_phase(phase_dir, yaml)
        total_hoisted += count
        all_warnings.extend(warnings)

    for w in all_warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    print(f"\nDone. Hoisted {total_hoisted} requirement(s) to per-phase files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
