"""Fixed workflow contracts captured before extracting the engine catalog."""

import json
from pathlib import Path

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification import workflows
from learn_to_cloud_shared.verification.core import VerificationWorkflow
from learn_to_cloud_shared.verification.workflows import register_workflow, workflow_for

_CONTRACTS = json.loads(Path(__file__).with_name("workflow_contracts.json").read_text())


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
        "steps": [
            {
                "params_type": type(step.params).__name__,
                "check_name": step.params.check_name,
                "task_id": step.task_id,
                "params": step.params.model_dump(mode="json"),
            }
            for step in workflow.steps
        ],
        "rubric": workflow.rubric.model_dump(mode="json") if workflow.rubric else None,
        "system_prompt": workflow.system_prompt,
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
