"""Contracts for managed labels, issue triage, and offline evaluation."""

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
WORKFLOW = ROOT / ".github" / "workflows" / "issue-triage.md"


@pytest.fixture
def label_setup():
    return SimpleNamespace(**runpy.run_path(str(SCRIPTS / "setup_issue_labels.py")))


@pytest.fixture
def evaluation():
    return SimpleNamespace(**runpy.run_path(str(SCRIPTS / "evaluate_issue_triage.py")))


@pytest.mark.unit
def test_label_plan_is_idempotent_and_preserves_unmanaged_labels(label_setup):
    desired = label_setup.load_definitions()
    unmanaged = label_setup.Label("bug", "ffffff", "Existing legacy label")
    assert label_setup.plan_labels(desired, [*desired, unmanaged]) == []
    assert label_setup.plan_labels(desired, []) == [
        ("create", label) for label in desired
    ]
    changed = label_setup.Label(desired[0].name.upper(), "ffffff", "Old description")
    assert label_setup.plan_labels(desired, [changed, *desired[1:]]) == [
        ("update", desired[0])
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid",
    [
        [],
        {},
        [{"name": "area:test", "color": "bad", "description": "Test"}],
        [{"name": "area:test", "color": "ffffff", "description": ""}],
        [
            {"name": "area:test", "color": "ffffff", "description": "Test"},
            {"name": "AREA:TEST", "color": "ffffff", "description": "Duplicate"},
        ],
    ],
)
def test_label_definitions_reject_invalid_metadata(label_setup, tmp_path, invalid):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        label_setup.load_definitions(path)


@pytest.mark.unit
def test_label_preview_reads_all_pages_and_never_writes(
    label_setup, monkeypatch, capsys
):
    runner = MagicMock(
        return_value=subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                [
                    [{"name": "legacy", "color": "ffffff", "description": None}],
                    [{"name": "other", "color": "000000", "description": ""}],
                ]
            ),
        )
    )
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr("sys.argv", ["setup_issue_labels.py"])
    label_setup.main()
    assert runner.call_count == 1
    command = runner.call_args.args[0]
    assert "--paginate" in command
    assert "--slurp" in command
    assert "--method" not in command
    assert "Preview only" in capsys.readouterr().out


@pytest.mark.unit
def test_label_apply_only_creates_and_updates_managed_definitions(
    label_setup, monkeypatch, capsys
):
    desired = label_setup.load_definitions()
    existing = [
        {"name": label.name, "color": label.color, "description": label.description}
        for label in desired[1:]
    ]
    existing[0]["description"] = "Old description"
    existing.append({"name": "legacy", "color": "ffffff", "description": "Leave alone"})
    runner = MagicMock(
        side_effect=[
            subprocess.CompletedProcess([], 0, stdout=json.dumps([existing])),
            subprocess.CompletedProcess([], 0, stdout="{}"),
            subprocess.CompletedProcess([], 0, stdout="{}"),
        ]
    )
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr("sys.argv", ["setup_issue_labels.py", "--apply"])
    label_setup.main()
    create, update = runner.call_args_list[1:]
    assert create.args[0][5] == "POST"
    assert update.args[0][5] == "PATCH"
    assert update.args[0][6].endswith("/labels/area%3Averification")
    assert json.loads(create.kwargs["input"])["name"] == "area:content"
    assert "name" not in json.loads(update.kwargs["input"])
    assert all("DELETE" not in call.args[0] for call in runner.call_args_list)
    assert "Applied 2 label changes" in capsys.readouterr().out


@pytest.mark.unit
def test_label_api_failure_is_not_reported_as_success(label_setup, monkeypatch, capsys):
    runner = MagicMock(
        side_effect=subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="Resource not accessible by integration"
        )
    )
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr("sys.argv", ["setup_issue_labels.py", "--apply"])
    with pytest.raises(SystemExit) as error:
        label_setup.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "Resource not accessible" in output.err
    assert "Applied" not in output.out


@pytest.mark.unit
def test_workflow_limits_metadata_changes_to_triggering_issue():
    frontmatter = WORKFLOW.read_text().split("---", 2)[1]
    workflow = yaml.safe_load(frontmatter)
    # PyYAML's YAML 1.1 loader interprets the GitHub Actions "on" key as True.
    trigger = workflow[True]
    assert trigger["issues"]["types"] == ["opened", "reopened"]
    assert workflow["permissions"] == {
        "contents": "read",
        "issues": "read",
        "copilot-requests": "write",
    }
    assert workflow["tools"]["bash"] is True
    assert workflow["tools"]["cli-proxy"] is True
    assert workflow["tools"]["edit"] is False
    github = workflow["tools"]["github"]
    assert github["mode"] == "gh-proxy"
    assert github["read-only"] is True
    assert github["min-integrity"] == "none"
    assert github["allowed-repos"] == ["learntocloud/learn-to-cloud-app"]
    outputs = workflow["safe-outputs"]
    assert set(outputs) == {
        "set-issue-type",
        "set-issue-field",
        "report-failure-as-issue",
        "report-failed-jobs",
        "activation-comments",
        "noop",
        "missing-tool",
        "missing-data",
        "report-incomplete",
    }
    assert outputs["report-failure-as-issue"] is False
    assert outputs["report-failed-jobs"] is False
    assert outputs["activation-comments"] is False
    assert outputs["noop"]["report-as-issue"] is False
    assert outputs["missing-tool"]["create-issue"] is False
    assert outputs["missing-data"]["create-issue"] is False
    assert outputs["report-incomplete"]["create-issue"] is False
    assert outputs["set-issue-type"]["allowed"] == ["Bug", "Feature"]
    assert outputs["set-issue-field"]["allowed-fields"] == ["Priority"]
    for name in ("set-issue-type", "set-issue-field"):
        config = outputs[name]
        assert config["issue-intent"] is True
        assert "target" not in config
        assert "github-token" not in config
        assert "allowed-repos" not in config
    assert not (ROOT / ".github/workflows/new-issue.yaml").exists()
    assert not (ROOT / ".github/workflows/agentics-maintenance.yml").exists()
    assert (ROOT / ".github/aw/actions-lock.json").exists()
    assert not (ROOT / ".github/aw/logs/.gitignore").exists()


@pytest.mark.unit
def test_workflow_pins_triage_to_an_exact_model():
    workflow = yaml.safe_load(WORKFLOW.read_text().split("---", 2)[1])
    assert workflow["engine"] == {"id": "copilot", "model": "copilot/gpt-5-mini"}
    compiled = yaml.safe_load(WORKFLOW.with_suffix(".lock.yml").read_text())
    for name in ("agent", "detection"):
        models = [
            step["env"]["COPILOT_MODEL"]
            for step in compiled["jobs"][name]["steps"]
            if "COPILOT_MODEL" in step.get("env", {})
        ]
        assert models
        assert all(model == "copilot/gpt-5-mini" for model in models)


@pytest.mark.unit
def test_compiled_workflow_uses_actions_token_for_copilot_inference():
    compiled_text = WORKFLOW.with_suffix(".lock.yml").read_text()
    compiled = yaml.safe_load(compiled_text)
    assert "${{ secrets.COPILOT_GITHUB_TOKEN }}" not in compiled_text
    for name in ("agent", "detection"):
        job = compiled["jobs"][name]
        assert job["permissions"]["copilot-requests"] == "write"
        inference_tokens = [
            step["env"]["COPILOT_GITHUB_TOKEN"]
            for step in job["steps"]
            if "COPILOT_GITHUB_TOKEN" in step.get("env", {})
        ]
        assert inference_tokens
        assert all(token == "${{ github.token }}" for token in inference_tokens)


@pytest.mark.unit
def test_compiled_workflow_uses_cli_proxy_and_blocks_failed_detection():
    compiled = yaml.safe_load(WORKFLOW.with_suffix(".lock.yml").read_text())
    assert "suggest_issue_type" not in compiled["jobs"]
    safe_job = compiled["jobs"]["safe_outputs"]
    assert "needs.detection.result == 'success'" in safe_job["if"]
    agent_steps = compiled["jobs"]["agent"]["steps"]
    cli_proxy = next(
        step for step in agent_steps if step.get("name") == "Start CLI Proxy"
    )
    assert cli_proxy["env"]["CLI_PROXY_IMAGE"].startswith("ghcr.io/github/gh-aw-mcpg:")
    assert "safeoutputs set_issue_type" in WORKFLOW.read_text()
    assert "safeoutputs set_issue_field" in WORKFLOW.read_text()
    all_steps = [
        step for job in compiled["jobs"].values() for step in job.get("steps", [])
    ]
    assert not any(
        "report_failed_jobs" in step.get("with", {}).get("script", "")
        for step in all_steps
    )
    for name in (
        "GH_AW_FAILURE_REPORT_AS_ISSUE",
        "GH_AW_NOOP_REPORT_AS_ISSUE",
        "GH_AW_REPORT_INCOMPLETE_CREATE_ISSUE",
    ):
        values = [
            step["env"][name] for step in all_steps if name in step.get("env", {})
        ]
        assert values and all(value == "false" for value in values)


@pytest.mark.unit
def test_evaluation_prompt_hides_expectations(evaluation):
    cases = json.loads(evaluation.CASES.read_text())
    prompt = evaluation.build_prompt(cases, WORKFLOW.read_text())
    assert '"expect"' not in prompt
    assert '"required_labels"' not in prompt
    assert "Do not use tools" in prompt
    assert len([case for case in cases if case["source"]]) == 20
    assert len({case["id"] for case in cases}) == len(cases)
    assert {"guard-preserve", "guard-injection"} <= {case["id"] for case in cases}


def decision(value):
    if value is None:
        return None
    return {
        "value": value,
        "rationale": "Supported by the supplied report.",
        "confidence": "MEDIUM",
    }


@pytest.mark.unit
def test_evaluation_scores_changes_and_rejects_missing_results(evaluation):
    cases = json.loads(evaluation.CASES.read_text())
    results = [
        {
            "id": case["id"],
            "issue_type": decision(case["expect"]["types"][0]),
            "priority": decision(case["expect"]["priorities"][0]),
            "labels": [decision(label) for label in case["expect"]["required_labels"]],
        }
        for case in cases
    ]
    assert evaluation.score(cases, results) == []
    results[0]["priority"] = decision("Urgent")
    assert len(evaluation.score(cases, results)) == 1
    with pytest.raises(ValueError, match="every case"):
        evaluation.score(cases, results[:-1])
    with pytest.raises(ValueError, match="unique"):
        evaluation.score(cases, [*results, results[0]])


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid",
    [
        {"value": "Bug", "confidence": "HIGH"},
        {"value": "Bug", "rationale": "Reason", "confidence": "certain"},
        {"value": "Bug", "rationale": "Reason", "confidence": "HIGH", "suggest": False},
        {"value": "Bug", "rationale": "Reason", "confidence": "HIGH", "close": True},
    ],
)
def test_evaluation_requires_intent_metadata(evaluation, invalid):
    with pytest.raises(ValueError):
        evaluation.change_value(invalid)
