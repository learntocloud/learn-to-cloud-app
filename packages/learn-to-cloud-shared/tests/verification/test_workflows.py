"""Direct callable wiring and fixed verification workflow contracts."""

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from functools import partial
from inspect import iscoroutinefunction, signature
from pathlib import Path

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification import workflows
from learn_to_cloud_shared.verification.core import Step, VerificationWorkflow
from learn_to_cloud_shared.verification.tasks.base import VerificationTask
from learn_to_cloud_shared.verification.workflows import register_workflow, workflow_for

_CONTRACTS = json.loads(Path(__file__).with_name("workflow_contracts.json").read_text())


def _step_contract(step: Step):
    check = step.check
    if isinstance(check, partial):
        assert not check.args
        function = check.func
        arguments = signature(function).bind_partial(**check.keywords)
        arguments.apply_defaults()
        kwargs = {
            key: value.model_dump(mode="json")
            if isinstance(value, VerificationTask)
            else list(value)
            if isinstance(value, tuple)
            else value
            for key, value in arguments.arguments.items()
        }
    else:
        function = check
        kwargs = {}
    assert iscoroutinefunction(check)
    signature(check).bind(object())
    return {
        "check": function.__name__,
        "check_name": step.name,
        "task_id": step.task_id,
        "kwargs": kwargs,
    }


def test_workflow_contract_covers_every_submission_type():
    assert set(_CONTRACTS) == {
        submission_type.value for submission_type in SubmissionType
    }


@pytest.mark.parametrize("submission_type", list(SubmissionType))
def test_workflow_configuration_matches_baseline(submission_type):
    workflow = workflow_for(submission_type)
    assert workflow is not None
    assert {
        "requires_username": workflow.requires_username,
        "steps": [_step_contract(step) for step in workflow.steps],
        "rubric": workflow.rubric.model_dump(mode="json") if workflow.rubric else None,
    } == _CONTRACTS[submission_type.value]


def test_duplicate_workflow_registration_preserves_original(monkeypatch):
    monkeypatch.setattr(workflows, "_WORKFLOW_REGISTRY", {})
    original = VerificationWorkflow(requires_username=True)
    register_workflow(SubmissionType.CTF_TOKEN, original)
    with pytest.raises(ValueError, match="Workflow already registered"):
        register_workflow(
            SubmissionType.CTF_TOKEN, VerificationWorkflow(requires_username=False)
        )
    assert workflow_for(SubmissionType.CTF_TOKEN) is original


def test_unknown_workflow_returns_none(monkeypatch):
    monkeypatch.setattr(workflows, "_WORKFLOW_REGISTRY", {})
    assert workflow_for(SubmissionType.CTF_TOKEN) is None


def test_step_declarations_are_immutable():
    step = workflow_for(SubmissionType.CTF_TOKEN).steps[0]
    with pytest.raises(FrozenInstanceError):
        step.name = "changed"


@pytest.mark.parametrize(
    "first",
    [
        "core",
        "checks.career",
        "checks.deployed_api",
        "checks.devops",
        "checks.github",
        "checks.security",
        "checks.tokens",
        "workflows",
        "engine",
    ],
)
def test_workflows_are_complete_in_fresh_import_orders(first):
    script = """
import importlib
import inspect
import sys

prefix = "learn_to_cloud_shared.verification."
first = sys.argv[1]
importlib.import_module(prefix + first)
if first == "core" or first.startswith("checks."):
    assert prefix + "workflows" not in sys.modules
    assert prefix + "engine" not in sys.modules

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.engine import run_verification
from learn_to_cloud_shared.verification.workflows import workflow_for

count = 0
for submission_type in SubmissionType:
    workflow = workflow_for(submission_type)
    assert workflow is not None
    for step in workflow.steps:
        assert inspect.iscoroutinefunction(step.check)
        inspect.signature(step.check).bind(object())
        count += 1
assert count == 10
assert prefix + "checks.registry" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script, first],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
