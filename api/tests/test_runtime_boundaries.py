"""Runtime modules and dependencies must not reach into development-only helpers."""

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_FILES = sorted((_ROOT / "api/src/learn_to_cloud").rglob("*.py"))
_TEST_MODULES = (
    "tests",
    "testing",
    "pytest",
    "pytest_asyncio",
    "unittest.mock",
    "learn_to_cloud.testing",
    "tests.support",
)


@pytest.mark.parametrize(
    "path", _RUNTIME_FILES, ids=lambda p: str(p.relative_to(_ROOT))
)
def test_runtime_imports_do_not_depend_on_test_support(path):
    imports = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.extend(
                f"{module}.{alias.name}" if module else alias.name
                for alias in node.names
            )

    assert not [
        name
        for name in imports
        if any(name == root or name.startswith(f"{root}.") for root in _TEST_MODULES)
    ]


def test_runtime_trees_do_not_contain_test_source():
    assert not [
        str(path.relative_to(_ROOT))
        for path in _RUNTIME_FILES
        if "testing" in path.parts
        or "tests" in path.parts
        or path.name.startswith("test_")
        or path.name == "conftest.py"
    ]


_PACKAGE_ROOT = _ROOT / "api/src/learn_to_cloud"
# Top-level learn_to_cloud modules each package may import (besides itself).
_ALLOWED_IMPORTS = {
    "core": set(),
    "schemas": {"models"},
    "curriculum": {"core", "schemas"},
    "verification": {"core", "schemas", "models", "repositories"},
    "repositories": {"core", "models", "verification"},
    "rendering": {"core", "schemas", "models", "verification"},
}
_LAYERED_FILES = [
    path
    for package in _ALLOWED_IMPORTS
    for path in sorted((_PACKAGE_ROOT / package).rglob("*.py"))
]


@pytest.mark.parametrize(
    "path", _LAYERED_FILES, ids=lambda p: str(p.relative_to(_ROOT))
)
def test_packages_import_only_lower_layers(path):
    """Lower layers never import services, routes, or the app entry point."""
    package = path.relative_to(_PACKAGE_ROOT).parts[0]
    allowed = _ALLOWED_IMPORTS[package] | {package}
    modules = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

    assert not [
        name
        for name in modules
        if name.split(".")[0] == "learn_to_cloud" and name.split(".")[1] not in allowed
    ]
