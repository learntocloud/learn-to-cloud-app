"""Reject Dependabot PRs that contain unreported direct dependency upgrades."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

_DEPENDENCY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_DEPENDABOT_TABLE_NAME = re.compile(r"^\|\s*\[([^\]]+)\]\(", re.MULTILINE)


def canonicalize(name: str) -> str:
    """Normalize a Python package name using the packaging specification."""
    name = name.split("[", 1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def lock_versions(content: str) -> dict[str, tuple[str, ...]]:
    """Return every locked version keyed by normalized package name."""
    versions: dict[str, set[str]] = {}
    for package in tomllib.loads(content).get("package", []):
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions.setdefault(canonicalize(name), set()).add(version)
    return {name: tuple(sorted(values)) for name, values in versions.items()}


def direct_dependencies(root: Path) -> set[str]:
    """Collect direct dependency names from workspace pyproject files."""
    dependencies: set[str] = set()
    for path in root.rglob("pyproject.toml"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        data = tomllib.loads(path.read_text())
        groups: list[list[object]] = []
        project = data.get("project", {})
        groups.append(project.get("dependencies", []))
        groups.extend(project.get("optional-dependencies", {}).values())
        groups.extend(data.get("dependency-groups", {}).values())
        for group in groups:
            for requirement in group:
                if not isinstance(requirement, str):
                    continue
                match = _DEPENDENCY_NAME.match(requirement)
                if match:
                    dependencies.add(canonicalize(match.group(1)))
    return dependencies


def declared_updates(body: str) -> set[str]:
    """Extract dependency names from Dependabot's update table."""
    return {
        canonicalize(match)
        for match in _DEPENDABOT_TABLE_NAME.findall(body)
    }


@dataclass(frozen=True)
class VersionChange:
    name: str
    before: tuple[str, ...]
    after: tuple[str, ...]


def version_changes(base: str, head: str) -> list[VersionChange]:
    """Compare two uv lockfiles."""
    before = lock_versions(base)
    after = lock_versions(head)
    return [
        VersionChange(name, before.get(name, ()), after.get(name, ()))
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    ]


def undeclared_direct_changes(
    changes: list[VersionChange],
    direct: set[str],
    declared: set[str],
) -> list[str]:
    """Find changed direct dependencies missing from Dependabot's PR table."""
    return sorted(
        change.name
        for change in changes
        if change.name in direct and change.name not in declared
    )


def format_versions(versions: tuple[str, ...]) -> str:
    return ", ".join(versions) if versions else "(not present)"


def render_summary(
    changes: list[VersionChange],
    direct: set[str],
    undeclared: list[str],
) -> str:
    """Render the complete lockfile delta for logs and job summaries."""
    lines = [
        "## Dependabot lockfile audit",
        "",
        "| Package | From | To | Dependency type |",
        "|---|---:|---:|---|",
    ]
    lines.extend(
        f"| `{change.name}` | {format_versions(change.before)} | "
        f"{format_versions(change.after)} | "
        f"{'direct' if change.name in direct else 'transitive'} |"
        for change in changes
    )
    if not changes:
        lines.append("| _No version changes_ | | | |")
    if undeclared:
        lines.extend(
            [
                "",
                "### Blocking unreported direct updates",
                "",
                *[f"- `{name}`" for name in undeclared],
            ]
        )
    return "\n".join(lines) + "\n"


def git_file(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--lockfile", default="uv.lock")
    args = parser.parse_args()

    root = Path.cwd()
    changes = version_changes(
        git_file(args.base_ref, args.lockfile),
        (root / args.lockfile).read_text(),
    )
    direct = direct_dependencies(root)
    declared = declared_updates(os.environ.get("DEPENDABOT_PR_BODY", ""))
    undeclared = undeclared_direct_changes(changes, direct, declared)
    summary = render_summary(changes, direct, undeclared)
    print(summary)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a") as output:
            output.write(summary)

    if undeclared:
        print(
            "Dependabot changed direct dependencies that its PR did not report. "
            "Regenerate the lockfile with targeted updates or split the PR.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
