"""Validate curriculum content for cross-file integrity (issue #462).

Runs the strict validators in ``content_yaml_loader.validate_content()``
against the currently-loaded YAML and exits non-zero on any violation.

Run from the package root::

    cd api && uv run python scripts/validate_content.py

Runs as the ``validate-content`` prek hook to catch broken content before it
ships.
"""

from __future__ import annotations

import sys

from learn_to_cloud.content_yaml_loader import (
    clear_cache,
    validate_content,
)


def main() -> int:
    clear_cache()
    errors = validate_content()
    if not errors:
        print("Content validation: OK")
        return 0

    print(f"Content validation: {len(errors)} error(s) found", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
