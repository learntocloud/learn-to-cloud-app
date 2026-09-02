"""Tests for the Dependabot lockfile audit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_dependabot_lock import (
    declared_updates,
    direct_dependencies,
    undeclared_direct_changes,
    version_changes,
)


def _lock(packages: list[tuple[str, str]]) -> str:
    return "\n".join(
        f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
        for name, version in packages
    )


class DependabotLockAuditTests(unittest.TestCase):
    def test_version_changes_include_unlisted_transitive_updates(self) -> None:
        changes = version_changes(
            _lock([("direct-package", "1.0"), ("transitive-package", "1.0")]),
            _lock([("direct-package", "1.1"), ("transitive-package", "2.0")]),
        )

        self.assertEqual(
            [change.name for change in changes],
            ["direct-package", "transitive-package"],
        )

    def test_declared_updates_parse_dependabot_table(self) -> None:
        body = (
            "| Package | From | To |\n"
            "| --- | --- | --- |\n"
            "| [Agent_Framework.Foundry](https://example.com) | `1` | `2` |\n"
        )

        self.assertEqual(declared_updates(body), {"agent-framework-foundry"})

    def test_unreported_direct_update_is_blocked(self) -> None:
        changes = version_changes(
            _lock([("reported", "1.0"), ("hidden-direct", "1.0")]),
            _lock([("reported", "1.1"), ("hidden-direct", "2.0")]),
        )

        self.assertEqual(
            undeclared_direct_changes(
                changes,
                {"reported", "hidden-direct"},
                {"reported"},
            ),
            ["hidden-direct"],
        )

    def test_direct_dependencies_cover_workspace_dependency_groups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                """
[project]
dependencies = ["Authlib>=1.7"]

[project.optional-dependencies]
test = ["pytest>=9"]

[dependency-groups]
dev = ["ruff==0.16"]
""".strip()
            )

            self.assertEqual(
                direct_dependencies(root),
                {"authlib", "pytest", "ruff"},
            )


if __name__ == "__main__":
    unittest.main()
