"""Contracts for managed labels, constrained triage, and offline evaluation."""

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
def test_workflow_limits_metadata_changes_to_triggering_issue(label_setup):
    frontmatter = WORKFLOW.read_text().split("---", 2)[1]
    workflow = yaml.safe_load(frontmatter)
    # PyYAML's YAML 1.1 loader interprets the GitHub Actions "on" key as True.
    trigger = workflow[True]
    assert trigger["issues"]["types"] == ["opened", "reopened"]
    assert trigger["roles"] == "all"
    assert workflow["permissions"] == {"contents": "read", "issues": "read"}
    assert workflow["tools"]["bash"] is False
    assert workflow["tools"]["cli-proxy"] is False
    github = workflow["tools"]["github"]
    assert github["read-only"] is True
    assert github["min-integrity"] == "none"
    assert github["allowed-repos"] == ["learntocloud/learn-to-cloud-app"]
    outputs = workflow["safe-outputs"]
    assert set(outputs) == {
        "add-labels",
        "set-issue-type",
        "set-issue-field",
        "steps",
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
    assert set(outputs["add-labels"]["allowed"]) == {
        label.name for label in label_setup.load_definitions()
    }
    assert outputs["add-labels"]["create-if-missing"] is False
    assert outputs["add-labels"]["pull-requests"] is False
    assert outputs["add-labels"]["max"] == 3
    assert outputs["set-issue-type"]["allowed"] == ["Bug", "Feature", "Task"]
    assert outputs["set-issue-field"]["allowed-fields"] == ["Priority"]
    for name in ("add-labels", "set-issue-type", "set-issue-field"):
        config = outputs[name]
        assert config["issue-intent"] is True
        assert config["target"] == "triggering"
        assert "github-token" not in config
        assert "allowed-repos" not in config
    assert not (ROOT / ".github/workflows/new-issue.yaml").exists()
    assert (ROOT / ".github/workflows/agentics-maintenance.yml").exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scenario", "exit_code", "query_count"),
    [
        ("valid", 0, 1),
        ("explicit-target", 0, 1),
        ("existing", 1, 1),
        ("closed", 1, 1),
        ("no-type", 0, 0),
        ("empty-type", 1, 0),
        ("unknown-type", 1, 0),
        ("missing-metadata", 1, 1),
        ("multiple", 1, 0),
        ("direct-apply", 1, 0),
        ("other-issue", 1, 0),
        ("bad-confidence", 1, 0),
        ("missing-rationale", 1, 0),
    ],
)
def test_type_validator_is_read_only_and_rejects_unsafe_batches(
    scenario, exit_code, query_count
):
    workflow = yaml.safe_load(WORKFLOW.read_text().split("---", 2)[1])
    script = workflow["safe-outputs"]["steps"][0]["with"]["script"]
    harness = """
const fs = require('node:fs');
const script = fs.readFileSync(0, 'utf8');
const scenario = process.argv[1];
const calls = [];
const issue = { id: 'triggering-id', state: 'OPEN', issueType: null };
const proposal = {
  type: 'set_issue_type', issue_type: 'Bug', rationale: 'A documented failure.',
  confidence: 'MEDIUM', suggest: true
};
if (scenario === 'existing') issue.issueType = { id: 'existing-type' };
if (scenario === 'closed') issue.state = 'CLOSED';
if (scenario === 'missing-metadata') delete issue.issueType;
if (scenario === 'empty-type') proposal.issue_type = '';
if (scenario === 'unknown-type') proposal.issue_type = 'Incident';
if (scenario === 'direct-apply') proposal.suggest = false;
if (scenario === 'other-issue') proposal.issue_number = 999;
if (scenario === 'explicit-target') {
  proposal.issue_number = '123';
  proposal.repo = 'learntocloud/learn-to-cloud-app';
}
if (scenario === 'bad-confidence') proposal.confidence = 'certain';
if (scenario === 'missing-rationale') delete proposal.rationale;
const items = scenario === 'multiple' ? [proposal, proposal] :
  scenario === 'no-type' ? [] : [proposal];
const github = {
  async graphql(query, variables) {
    calls.push({ query, variables });
    if (!/^\\s*query\\(/.test(query)) throw new Error('Only reads are permitted');
    return { repository: { issue } };
  }
};
const context = {
  repo: { owner: 'learntocloud', repo: 'learn-to-cloud-app' },
  payload: { issue: { number: 123 } }
};
const core = { info() {} };
const env = { GH_AW_AGENT_OUTPUT: '/agent.json' };
const readOutput = name => {
  if (name !== 'node:fs') throw new Error('Unexpected module');
  return { readFileSync(path) {
    if (path !== '/agent.json') throw new Error('Unexpected file');
    return JSON.stringify({ items });
  } };
};
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
new AsyncFunction('require', 'github', 'context', 'core', 'process', script)(
  readOutput, github, context, core, { env }
).then(() => process.stdout.write(JSON.stringify({ calls })))
 .catch(error => {
   process.stdout.write(JSON.stringify({ calls, error: error.message }));
   process.exitCode = 1;
 });
"""
    result = subprocess.run(
        ["node", "-e", harness, scenario],
        input=script,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == exit_code, result.stderr
    output = json.loads(result.stdout)
    assert len(output["calls"]) == query_count
    assert all("mutation(" not in call["query"] for call in output["calls"])
    if query_count:
        assert output["calls"][0]["variables"] == {
            "owner": "learntocloud",
            "repo": "learn-to-cloud-app",
            "number": 123,
        }


@pytest.mark.unit
def test_compiled_workflow_validates_before_processing_and_blocks_failed_detection():
    compiled = yaml.safe_load(WORKFLOW.with_suffix(".lock.yml").read_text())
    assert "suggest_issue_type" not in compiled["jobs"]
    safe_job = compiled["jobs"]["safe_outputs"]
    assert "needs.detection.result == 'success'" in safe_job["if"]
    steps = safe_job["steps"]
    setup = next(
        index
        for index, step in enumerate(steps)
        if step.get("id") == "setup-agent-output-env"
    )
    validator = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Validate type proposals before safe outputs"
    )
    processor = next(
        index
        for index, step in enumerate(steps)
        if "process_safe_outputs.cjs" in step.get("with", {}).get("script", "")
    )
    assert setup < validator < processor
    assert steps[validator]["env"]["GH_AW_AGENT_OUTPUT"] == (
        "${{ steps.setup-agent-output-env.outputs.GH_AW_AGENT_OUTPUT }}"
    )
    assert not steps[validator].get("continue-on-error")
    assert "if" not in steps[processor]
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
