"""Compile the authored curriculum YAML into the canonical curriculum.json artifact.

Runs the strict deterministic compiler in ``curriculum/compiler.py`` and
writes ``curriculum.json`` next to ``phases/`` and ``schemas/`` under
``content/``. That file is committed to the repo and packaged as
``learn-to-cloud`` wheel data (see ``pyproject.toml``).

Run from the repository root::

    uv run python scripts/compile_curriculum.py

Pass ``--previous-artifact PATH`` to also enforce the curriculum_version
policy (must not decrease; may repeat only if content is unchanged)
against a prior artifact. CI does this against the artifact committed
at the PR base / pre-push SHA (see .github/workflows/ci.yml). The
``compile-curriculum`` prek hook catches drift from the committed copy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from learn_to_cloud.curriculum.compiler import (
    ContentCompileError,
    compile_and_write,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--previous-artifact",
        type=Path,
        default=None,
        help="Prior curriculum.json to check the curriculum_version policy against.",
    )
    args = parser.parse_args(argv)

    try:
        path = compile_and_write(previous_artifact_path=args.previous_artifact)
    except ContentCompileError as exc:
        print(f"Curriculum compile failed: {exc}", file=sys.stderr)
        return 1

    print(f"Curriculum compiled: OK -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
