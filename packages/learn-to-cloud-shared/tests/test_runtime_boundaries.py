"""Runtime modules and dependencies must not reach into development-only helpers."""

import ast
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_RUNTIME_ROOTS = (
    _ROOT / "api/src/learn_to_cloud",
    _ROOT / "packages/learn-to-cloud-shared/src/learn_to_cloud_shared",
)
_RUNTIME_FILES = sorted(
    [
        *(path for root in _RUNTIME_ROOTS for path in root.rglob("*.py")),
        _ROOT / "apps/verification-functions/function_app.py",
        _ROOT / "apps/verification-functions/verification_agents.py",
    ]
)
_TEST_MODULES = (
    "tests",
    "testing",
    "pytest",
    "pytest_asyncio",
    "unittest.mock",
    "learn_to_cloud_shared.testing",
    "learn_to_cloud_shared_test_support",
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


@pytest.mark.parametrize(
    "member",
    ["api", "packages/learn-to-cloud-shared", "apps/verification-functions"],
)
def test_shared_test_support_is_only_a_development_dependency(member):
    with (_ROOT / member / "pyproject.toml").open("rb") as manifest:
        config = tomllib.load(manifest)

    assert "learn-to-cloud-shared-test-support" in config["dependency-groups"]["dev"]
    assert not any(
        dependency.startswith("learn-to-cloud-shared-test-support")
        for dependency in config["project"]["dependencies"]
    )
    assert config["tool"]["uv"]["sources"]["learn-to-cloud-shared-test-support"] == {
        "workspace": True
    }


def test_runtime_trees_do_not_contain_test_source():
    assert not [
        str(path.relative_to(_ROOT))
        for path in _RUNTIME_FILES
        if "testing" in path.parts
        or "tests" in path.parts
        or path.name.startswith("test_")
        or path.name == "conftest.py"
    ]
