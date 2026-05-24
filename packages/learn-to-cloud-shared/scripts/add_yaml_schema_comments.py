"""Add yaml-language-server schema comments to every curriculum YAML.

For each ``_phase.yaml`` and every other ``*.yaml`` topic file in
``content/phases/``, prepend a comment that points editors (with the
YAML language server) at the appropriate JSON Schema, e.g.::

    # yaml-language-server: $schema=../../schemas/phase.schema.json

Idempotent: skips files that already have a schema comment on line 1.

Run from the package root::

    cd packages/learn-to-cloud-shared && \
        uv run python scripts/add_yaml_schema_comments.py
"""

from __future__ import annotations

import sys
from pathlib import Path

CONTENT_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "learn_to_cloud_shared"
    / "content"
    / "phases"
)

SCHEMA_COMMENT_PREFIX = "# yaml-language-server: $schema="
PHASE_SCHEMA_REL = "../../schemas/phase.schema.json"
TOPIC_SCHEMA_REL = "../../schemas/topic.schema.json"
REQUIREMENT_SCHEMA_REL = "../../../schemas/requirement.schema.json"


def _ensure_schema_comment(path: Path, schema_rel: str) -> bool:
    """Prepend the schema comment if missing. Returns True if added."""
    text = path.read_text(encoding="utf-8")
    first_line = text.split("\n", 1)[0] if text else ""
    if first_line.startswith(SCHEMA_COMMENT_PREFIX):
        return False
    comment = f"{SCHEMA_COMMENT_PREFIX}{schema_rel}\n"
    path.write_text(comment + text, encoding="utf-8")
    return True


def main() -> int:
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}", file=sys.stderr)
        return 1

    added = 0
    for phase_dir in sorted(CONTENT_DIR.iterdir()):
        if not phase_dir.is_dir() or not phase_dir.name.startswith("phase"):
            continue
        for yaml_file in sorted(phase_dir.glob("*.yaml")):
            schema = (
                PHASE_SCHEMA_REL
                if yaml_file.name == "_phase.yaml"
                else TOPIC_SCHEMA_REL
            )
            if _ensure_schema_comment(yaml_file, schema):
                rel = yaml_file.relative_to(CONTENT_DIR.parent.parent.parent.parent)
                print(f"  + schema comment -> {rel}")
                added += 1

        # Per-phase requirements/ directory (issue #470).
        req_dir = phase_dir / "requirements"
        if req_dir.is_dir():
            for req_file in sorted(req_dir.glob("*.yaml")):
                if _ensure_schema_comment(req_file, REQUIREMENT_SCHEMA_REL):
                    rel = req_file.relative_to(CONTENT_DIR.parent.parent.parent.parent)
                    print(f"  + schema comment -> {rel}")
                    added += 1

    print(f"\nDone. Added schema comment to {added} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
