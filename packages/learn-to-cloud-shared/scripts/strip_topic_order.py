"""Remove the ``order`` field from every curriculum topic YAML (issue #463).

After the topic schema refactor, topic order is derived from the
position in ``_phase.yaml``'s ``topics:`` slug list (one source of
truth). This script strips the now-redundant ``order: <int>`` field
from every topic file.

Idempotent: skips files that don't have ``order``.

Run from the package root::

    cd packages/learn-to-cloud-shared && \\
        uv run python scripts/strip_topic_order.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

CONTENT_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "learn_to_cloud_shared"
    / "content"
    / "phases"
)


def _strip_order(doc: CommentedMap) -> bool:
    if "order" not in doc:
        return False
    del doc["order"]
    return True


def main() -> int:
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}", file=sys.stderr)
        return 1

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096

    stripped = 0
    for phase_dir in sorted(CONTENT_DIR.iterdir()):
        if not phase_dir.is_dir() or not phase_dir.name.startswith("phase"):
            continue
        for yaml_file in sorted(phase_dir.glob("*.yaml")):
            if yaml_file.name == "_phase.yaml":
                continue  # phase files keep their own ``order``
            with yaml_file.open(encoding="utf-8") as f:
                doc = yaml.load(f)
            if not isinstance(doc, CommentedMap):
                continue
            if _strip_order(doc):
                with yaml_file.open("w", encoding="utf-8") as f:
                    yaml.dump(doc, f)
                rel = yaml_file.relative_to(CONTENT_DIR.parent.parent.parent.parent)
                print(f"  - order removed from {rel}")
                stripped += 1

    print(f"\nDone. Stripped 'order' from {stripped} topic file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
