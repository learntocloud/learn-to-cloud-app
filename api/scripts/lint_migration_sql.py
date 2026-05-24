"""Lint new Alembic migration SQL with squawk.

Finds migration files that were added (not modified) compared to the
base branch, generates the SQL each migration would run, and feeds it
to squawk for safety checks.

Usage from the api/ directory::

    uv run python scripts/lint_migration_sql.py [--base origin/main]

Exit codes:
    0  No new migrations, or all new migrations pass squawk.
    1  Squawk found issues in one or more migrations.
    2  Script error (bad revision, SQL generation failure, etc.).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _get_new_migration_files(base: str) -> list[Path]:
    """Return migration files added (not modified) vs the base branch."""
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=A",
                base,
                "--",
                str(VERSIONS_DIR),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"git diff failed: {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(2)

    files = []
    for line in result.stdout.strip().splitlines():
        path = Path(line)
        if path.suffix == ".py" and path.name != "__init__.py":
            files.append(path)
    return files


def _revision_id_from_file(path: Path) -> str:
    """Extract the revision ID (filename stem) from a migration file."""
    return path.stem


def _get_down_revision(script_dir: ScriptDirectory, rev_id: str) -> str:
    """Get the down_revision for a given revision ID."""
    rev = script_dir.get_revision(rev_id)
    if rev is None:
        print(f"Could not find revision {rev_id}", file=sys.stderr)
        sys.exit(2)
    down = rev.down_revision
    if down is None:
        return "base"
    if isinstance(down, (list, tuple)):
        # Merge migration; use the first parent.
        return down[0]
    return down


def _generate_sql(down_rev: str, rev_id: str) -> str | None:
    """Run alembic upgrade --sql for one revision range."""
    range_spec = f"{down_rev}:{rev_id}"
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "--sql", range_spec],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"alembic upgrade --sql {range_spec} failed:\n{result.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    return result.stdout


def _run_squawk(sql: str, label: str) -> bool:
    """Run squawk on SQL text. Returns True if clean."""
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write(sql)
        f.flush()
        result = subprocess.run(
            ["uv", "run", "squawk", f.name],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        print(f"\n--- squawk issues in {label} ---")
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint new Alembic migrations with squawk."
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Git ref to diff against (default: origin/main)",
    )
    args = parser.parse_args()

    new_files = _get_new_migration_files(args.base)
    if not new_files:
        print("No new migration files found. Nothing to lint.")
        return 0

    print(f"Found {len(new_files)} new migration(s) to lint:")
    for f in new_files:
        print(f"  {f.name}")

    cfg = Config("alembic.ini")
    script_dir = ScriptDirectory.from_config(cfg)

    failed = False
    for migration_file in new_files:
        rev_id = _revision_id_from_file(migration_file)
        down_rev = _get_down_revision(script_dir, rev_id)

        sql = _generate_sql(down_rev, rev_id)
        if sql is None:
            print(
                f"Skipping {rev_id}: could not generate SQL",
                file=sys.stderr,
            )
            failed = True
            continue

        if not _run_squawk(sql, rev_id):
            failed = True

    if failed:
        print("\nSquawk found issues. Fix them before merging.")
        return 1

    print("\nAll new migrations passed squawk lint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
