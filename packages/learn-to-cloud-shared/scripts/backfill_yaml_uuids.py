"""Backfill UUIDs into curriculum YAML files (one-time script).

Walks every YAML file in ``content/phases/`` and adds a ``uuid`` field
to every curriculum entity that lacks one:

- Phase (``_phase.yaml`` top-level)
- HandsOnRequirement (``hands_on_verification.requirements[]`` in phase files)
- Topic (each topic file's top-level)
- LearningObjective (``learning_objectives[]`` in topic files)
- LearningStep (``learning_steps[]`` in topic files)

Uses ruamel.yaml in round-trip mode to preserve comments, formatting,
quote styles, and key order as much as possible. The added ``uuid``
field is inserted at the top of each mapping.

UUIDs are generated with uuid7 if available (sortable, time-ordered),
falling back to uuid4. UUIDs are written as strings.

Idempotent: re-running skips entities that already have a uuid.

Run from the package root::

    cd packages/learn-to-cloud-shared && uv run python scripts/backfill_yaml_uuids.py

After committing the resulting YAML changes, this script should not
need to run again -- new content should include ``uuid`` from the start
(generated via ``uuid7()`` in editor templates).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

# uuid7 was added in Python 3.14; fall back to uuid4 on older runtimes.
_gen_uuid = getattr(uuid, "uuid7", uuid.uuid4)

CONTENT_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "learn_to_cloud_shared"
    / "content"
    / "phases"
)


def _new_uuid_str() -> str:
    return str(_gen_uuid())


def _ensure_uuid(node: Any) -> bool:
    """Add a uuid key to a mapping if missing. Returns True if added."""
    if not isinstance(node, CommentedMap):
        return False
    if "uuid" in node:
        return False
    node.insert(0, "uuid", _new_uuid_str())
    return True


def _backfill_phase(doc: CommentedMap) -> int:
    """Add UUIDs to a phase document. Returns count of UUIDs added."""
    added = 0
    if _ensure_uuid(doc):
        added += 1
    hov = doc.get("hands_on_verification")
    if isinstance(hov, CommentedMap):
        for req in hov.get("requirements") or []:
            if _ensure_uuid(req):
                added += 1
    return added


def _backfill_topic(doc: CommentedMap) -> int:
    """Add UUIDs to a topic document. Returns count of UUIDs added."""
    added = 0
    if _ensure_uuid(doc):
        added += 1
    for obj in doc.get("learning_objectives") or []:
        if _ensure_uuid(obj):
            added += 1
    for step in doc.get("learning_steps") or []:
        if _ensure_uuid(step):
            added += 1
    return added


def main() -> int:
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}", file=sys.stderr)
        return 1

    yaml = YAML()
    yaml.preserve_quotes = True
    # Use a very large width so ruamel doesn't re-wrap long string fields.
    # Existing YAML files had inconsistent wrap widths from prior tooling;
    # unifying on "one line per string" makes future diffs easier to read.
    yaml.width = 4096

    total_files = 0
    total_added = 0

    for phase_dir in sorted(CONTENT_DIR.iterdir()):
        if not phase_dir.is_dir() or not phase_dir.name.startswith("phase"):
            continue

        for yaml_file in sorted(phase_dir.glob("*.yaml")):
            with yaml_file.open(encoding="utf-8") as f:
                doc = yaml.load(f)
            if not isinstance(doc, CommentedMap):
                continue

            if yaml_file.name == "_phase.yaml":
                added = _backfill_phase(doc)
            else:
                added = _backfill_topic(doc)

            if added > 0:
                with yaml_file.open("w", encoding="utf-8") as f:
                    yaml.dump(doc, f)
                rel = yaml_file.relative_to(CONTENT_DIR.parent.parent.parent.parent)
                print(f"  +{added} uuid(s) -> {rel}")
                total_files += 1
                total_added += added

    print(f"\nDone. Added {total_added} uuid(s) across {total_files} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
