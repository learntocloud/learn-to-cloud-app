"""Validate curriculum content for cross-file integrity (issue #462).

Runs the strict validators in ``content_yaml_loader.validate_content()``
against the currently-loaded YAML and exits non-zero on any violation.

Run from the package root::

    cd packages/learn-to-cloud-shared && uv run python scripts/validate_content.py

Used by CI to catch broken content before it ships.
"""

from __future__ import annotations

import sys

# Register the minimal settings profile (WorkerSettings) before importing
# anything that touches the shared settings tree. The shared package
# defaults to WebSettings, which demands GitHub OAuth secrets in
# production -- irrelevant for a content validator. WorkerSettings is
# enough; it has content_dir_path. This MUST run before the YAML loader
# is imported, so the import below is intentionally out of order.
from learn_to_cloud_shared.core.config import (
    WorkerSettings,
    configure_settings,
)

configure_settings(WorkerSettings)

from learn_to_cloud_shared.content_yaml_loader import (  # noqa: E402
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
