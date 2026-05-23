"""Create a new Alembic migration with a sequential ``NNNN_descriptive_slug`` id.

Wraps ``alembic revision`` so authors never get the default hex revision id.
The next sequential number is derived from the highest ``NNNN_*`` filename in
``alembic/versions/``; the message is slugified into the rest of the id.

Run from ``api/``::

    uv run python scripts/new_migration.py "drop redundant users index" [--autogenerate]

Optional flags forwarded to ``alembic revision``:

* ``--autogenerate`` — populate the migration from model diff
* ``--head <id>``    — specify a head other than the current one
* ``--splice``       — splice into an existing chain (rare; intentional branching)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"
_NEXT_ID_PATTERN = re.compile(r"^(\d{4})_")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _next_revision_number() -> int:
    nums: list[int] = []
    for f in _VERSIONS_DIR.glob("*.py"):
        match = _NEXT_ID_PATTERN.match(f.stem)
        if match:
            nums.append(int(match.group(1)))
    return (max(nums) + 1) if nums else 1


def _slugify(message: str) -> str:
    slug = _SLUG_PATTERN.sub("_", message.strip().lower()).strip("_")
    if not slug:
        raise SystemExit("Message produced an empty slug; provide more words.")
    return slug


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="Short imperative description.")
    parser.add_argument(
        "--autogenerate",
        action="store_true",
        help="Populate the new migration from model diff.",
    )
    parser.add_argument(
        "--head",
        help="Specify a head other than the current default head.",
    )
    parser.add_argument(
        "--splice",
        action="store_true",
        help="Allow splicing into an existing chain (intentional branching).",
    )
    args = parser.parse_args()

    next_num = _next_revision_number()
    slug = _slugify(args.message)
    rev_id = f"{next_num:04d}_{slug}"

    cmd = [
        "uv",
        "run",
        "alembic",
        "revision",
        "-m",
        args.message,
        "--rev-id",
        rev_id,
    ]
    if args.autogenerate:
        cmd.append("--autogenerate")
    if args.head:
        cmd.extend(["--head", args.head])
    if args.splice:
        cmd.append("--splice")

    print(f"Creating revision: {rev_id}")
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
