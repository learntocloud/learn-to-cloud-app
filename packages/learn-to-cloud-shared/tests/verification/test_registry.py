"""Explicit registration and fresh-process catalog wiring contracts."""

import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from learn_to_cloud_shared.verification.checks import (
    career,
    deployed_api,
    deployment_architecture,
    devops,
    github,
    rubric,
    security,
    tokens,
)
from learn_to_cloud_shared.verification.checks.registry import CHECK_REGISTRY
from learn_to_cloud_shared.verification.core import (
    CheckParams,
    CheckRegistry,
    StepResult,
)
from learn_to_cloud_shared.verification.tasks.phase4 import (
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)

_BUILT_INS = [
    (github.CIStatusParams(), github._check_github_ci_passing),
    (github.ProfileReadmeCheckParams(), github._check_profile_readme),
    (github.RepoForkCheckParams(), github._check_repo_fork),
    (tokens.CtfTokenCheckParams(), tokens._check_ctf_token),
    (tokens.NetworkingTokenCheckParams(), tokens._check_networking_token),
    (deployed_api.DeployedApiCheckParams(), deployed_api._check_deployed_api),
    (
        deployment_architecture.DeploymentArchitectureGateParams(),
        deployment_architecture._check_deployment_architecture_gate,
    ),
    (
        deployment_architecture.DeploymentArchitectureReviewParams(
            task=DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK
        ),
        deployment_architecture._check_deployment_architecture_review,
    ),
    (devops.DevopsRequiredFilesParams(), devops._check_devops_required_files),
    (devops.PublicGhcrImageParams(), devops._check_public_ghcr_image),
    (
        rubric.LLMRubricReviewParams(
            task=DEVOPS_IMPLEMENTATION_RUBRIC_TASK, discover_paths=True
        ),
        rubric._check_llm_rubric_review,
    ),
    (security.CodeQLStatusParams(), security._check_codeql_status),
    (
        security.SecurityScanningReviewParams(task=SECURITY_SCANNING_RUBRIC_TASK),
        security._check_security_scanning_review,
    ),
    (career.CareerReflectionGateParams(), career._check_career_reflection_gate),
    (
        career.CareerReflectionReviewParams(task=CAREER_REFLECTION_RUBRIC_TASK),
        career._check_career_reflection_review,
    ),
]


def test_catalog_contains_exactly_the_fifteen_builtin_adapters():
    assert CHECK_REGISTRY._checks == {
        type(params): check for params, check in _BUILT_INS
    }
    for params, check in _BUILT_INS:
        assert CHECK_REGISTRY.check_for(params) is check


class CustomParams(CheckParams):
    check_name = "custom"


class DerivedParams(CustomParams):
    check_name = "derived"


def test_constructor_rejects_duplicate_types():
    check = AsyncMock()
    with pytest.raises(ValueError, match="Check already registered: custom"):
        CheckRegistry([(CustomParams, check), (CustomParams, check)])


def test_duplicate_registration_does_not_replace_original():
    original = AsyncMock()
    registry = CheckRegistry([(CustomParams, original)])
    with pytest.raises(ValueError, match="Check already registered: custom"):
        registry.register(CustomParams, AsyncMock())
    assert registry.check_for(CustomParams()) is original


@pytest.mark.parametrize("params", [CustomParams(), DerivedParams()])
def test_empty_registry_rejects_unknown_types(params):
    with pytest.raises(
        KeyError, match=f"No check registered for '{params.check_name}'"
    ):
        CheckRegistry().check_for(params)


def test_dispatch_has_no_inherited_fallback():
    registry = CheckRegistry([(CustomParams, AsyncMock())])
    with pytest.raises(KeyError, match="No check registered for 'derived'"):
        registry.check_for(DerivedParams())


async def test_isolated_registry_preserves_callback_and_result_identity():
    result = StepResult(passed=True)
    check = AsyncMock(return_value=result)
    registry = CheckRegistry([(CustomParams, check)])
    params = CustomParams()
    context = object()
    assert await registry.check_for(params)(context, params) is result
    check.assert_awaited_once_with(context, params)
    with pytest.raises(KeyError):
        CHECK_REGISTRY.check_for(params)


@pytest.mark.parametrize(
    "first",
    ["core", "checks.github", "workflows", "checks.registry", "engine"],
)
def test_catalog_is_complete_in_fresh_import_orders(first):
    script = """
import importlib
import sys

prefix = "learn_to_cloud_shared.verification."
first = sys.argv[1]
importlib.import_module(prefix + first)
if first in {"core", "checks.github"}:
    assert prefix + "checks.registry" not in sys.modules
    assert prefix + "workflows" not in sys.modules
    assert prefix + "engine" not in sys.modules

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.checks.registry import CHECK_REGISTRY
from learn_to_cloud_shared.verification.engine import run_verification
from learn_to_cloud_shared.verification.workflows import workflow_for

assert len(CHECK_REGISTRY._checks) == 15
for submission_type in SubmissionType:
    workflow = workflow_for(submission_type)
    assert workflow is not None
    for step in workflow.steps:
        assert callable(CHECK_REGISTRY.check_for(step.params))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, first],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
