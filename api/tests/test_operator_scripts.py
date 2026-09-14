"""Regression coverage for local and operational script cleanup."""

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
ISSUE_TEMPLATES = SCRIPTS.parent / ".github" / "ISSUE_TEMPLATE"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "required"),
    [
        ("content_problem.yml", {"location", "page-url", "problem"}),
        (
            "app_problem.yml",
            {
                "location",
                "page-url",
                "environment",
                "problem",
                "steps",
                "error",
                "impact",
            },
        ),
    ],
)
def test_issue_forms_require_reporter_details_without_presumed_bug(filename, required):
    form = yaml.safe_load((ISSUE_TEMPLATES / filename).read_text())
    fields = {field["id"]: field for field in form["body"] if "id" in field}

    assert form["name"] and form["description"]
    assert "type" not in form
    assert form.get("labels", []) == (
        ["area:content"] if filename == "content_problem.yml" else []
    )
    assert {
        field_id
        for field_id, field in fields.items()
        if field.get("validations", {}).get("required")
    } == required
    assert {"location", "page-url", "diagnostics"} <= fields.keys()
    assert all("value" not in field["attributes"] for field in fields.values())
    assert len(fields) == (5 if filename == "content_problem.yml" else 8)
    instructions = form["body"][0]["attributes"]["value"]
    assert "/discussions" in instructions
    assert "tokens" in instructions and "credentials" in instructions


@pytest.mark.unit
def test_issue_intake_keeps_support_in_discussions_and_disables_blank_reports():
    config = yaml.safe_load((ISSUE_TEMPLATES / "config.yml").read_text())

    assert config["blank_issues_enabled"] is False
    assert any(
        link["url"].endswith("/discussions")
        and "help" in link["about"]
        and "features" in link["about"]
        for link in config["contact_links"]
    )
    assert not (ISSUE_TEMPLATES / "bug_report.md").exists()


@pytest.mark.unit
@pytest.mark.parametrize("event_type", ["pointerdown", "keydown", "click"])
@pytest.mark.parametrize("template", ["content_problem.yml", "app_problem.yml"])
def test_report_issue_prefills_form_context_without_private_data(template, event_type):
    harness = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
const template = process.argv[2];
const eventType = process.argv[3];
const script = [...source.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .find(match => match[1].includes("function decorateIssueLink"))[1];
const content = template === "content_problem.yml";
const pagePath = content ? "/phase/1/linux" : "/verifications/phase/3";
const context = content ? "phase=1, topic=linux" : "requirement=ci-status";
const initialUrl = "https://github.com/learntocloud/learn-to-cloud-app/issues/new"
  + "?template=" + template + "&labels=bug&body=obsolete";
const anchor = {
  href: initialUrl,
  dataset: {
    issueTitle: content ? "Issue with Linux & shell" : "Verification: CI Status",
    issueContext: context,
    issueLabels: "bug",
    submittedValue: "private-submitted-value",
  },
  getAttribute(name) { assert.equal(name, "href"); return this.href; },
};
const handlers = {};
vm.runInNewContext(script, {
  URL,
  Date,
  navigator: { userAgent: "Test Browser/1.0" },
  window: { location: {
    href: "https://private-user:private-password@learn.example" + pagePath
      + "?token=private-token&history_page=2#private-fragment",
  } },
  document: {
    title: "private-account-name",
    get cookie() { throw Error("Do not collect cookies"); },
    addEventListener(name, callback, capture) {
      assert.equal(capture, true);
      handlers[name] = callback;
    },
  },
});
const target = {
  closest(selector) {
    assert.equal(selector, "a[data-report-issue]");
    return anchor;
  },
};
handlers.keydown({ key: "Escape", target });
handlers.pointerdown({ target: {} });
assert.equal(anchor.href, initialUrl);
handlers[eventType]({ key: "Enter", target });
assert.equal(anchor.dataset.issueDecorated, "1");
const decoratedUrl = anchor.href;
handlers.click({ target });
assert.equal(anchor.href, decoratedUrl);
process.stdout.write(JSON.stringify({ href: decoratedUrl, pagePath }));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            harness,
            str(SCRIPTS.parent / "api/src/learn_to_cloud/templates/base.html"),
            template,
            event_type,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    params = parse_qs(urlparse(output["href"]).query)
    assert params["template"] == [template]
    assert params["page-url"] == ["https://learn.example" + output["pagePath"]]
    assert params["location"] == [
        "phase=1, topic=linux"
        if template == "content_problem.yml"
        else "phase=3, requirement=ci-status"
    ]
    assert params["title"] == [
        "Issue with Linux & shell"
        if template == "content_problem.yml"
        else "Verification: CI Status"
    ]
    diagnostics = params["diagnostics"][0]
    assert "Browser: Test Browser/1.0" in diagnostics
    assert "Reported at: " in diagnostics
    assert "private-" not in output["href"]
    assert "history_page" not in output["href"]
    form = yaml.safe_load((ISSUE_TEMPLATES / template).read_text())
    fields = {field["id"] for field in form["body"] if "id" in field}
    assert params.keys() - {"template", "title"} <= fields
    assert not {"body", "labels", "problem", "steps", "error", "impact"} & params.keys()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scenario", "exit_code"),
    [
        ("success", 0),
        ("failed_checks", 2),
        ("legacy_body", 2),
        ("prefilled_symptoms", 2),
        ("wrong_template", 2),
        ("private_page", 2),
        ("wrong_repository", 2),
        ("exception", 1),
    ],
)
def test_issue_report_closes_browser_before_exit(scenario, exit_code):
    harness = """
const fs = require("node:fs");
const vm = require("node:vm");
const script = process.argv[1];
const scenario = process.argv[2];
let closed = false;
let currentUrl = "";
const page = {
  on() {},
  async goto(url) {
    if (scenario === "exception") throw new Error("Navigation failed");
    currentUrl = url;
  },
  async waitForSelector() {},
  async evaluate() {},
  async waitForTimeout() {},
  async getAttribute(selector) {
    if (selector.startsWith('a[href^=')) return "/phase/1/test-topic";
    const dashboard = currentUrl.endsWith("/dashboard");
    const issue = new URL(scenario === "wrong_repository"
      ? "https://github.com/example/project/issues/new"
      : "https://github.com/learntocloud/learn-to-cloud-app/issues/new");
    issue.searchParams.set("title", dashboard ? "Dashboard Issue" : "Issue with topic");
    issue.searchParams.set("template", dashboard
      ? "app_problem.yml" : "content_problem.yml");
    issue.searchParams.set("location", dashboard
      ? "page=dashboard" : "phase=1, topic=test-topic");
    issue.searchParams.set("page-url", currentUrl);
    issue.searchParams.set("diagnostics", scenario === "failed_checks" ? "" : [
      "Reported at: 2026-09-14T12:00:00.000Z",
      "Browser: Test"
    ].join("\\n"));
    if (scenario === "legacy_body") {
      issue.searchParams.delete("template");
      issue.searchParams.set("labels", "bug");
      issue.searchParams.set("body", "**Page:** " + currentUrl);
    }
    if (scenario === "prefilled_symptoms") {
      issue.searchParams.set("problem", "Describe your problem");
      issue.searchParams.set("steps", "1.");
    }
    if (scenario === "wrong_template") {
      issue.searchParams.set("template", "bug_report.md");
    }
    if (scenario === "private_page") {
      issue.searchParams.set("page-url", currentUrl + "?token=private-token#secret");
    }
    return issue.toString();
  }
};
const browser = {
  async newContext() {
    return { async addCookies() {}, async newPage() { return page; } };
  },
  async close() {
    await new Promise(resolve => setImmediate(resolve));
    closed = true;
  }
};
const sandbox = {
  __dirname: require("node:path").dirname(script),
  URL,
  process,
  console: { log() {}, error() {} },
  require(name) {
    if (name === "playwright") {
      return { chromium: { async launch() { return browser; } } };
    }
    if (name === "child_process") {
      return { execSync() { return JSON.stringify({
        cookie_name: "local-session", cookie_value: "local-only",
        domain: "localhost", path: "/"
      }); } };
    }
    return require(name);
  }
};
(async () => {
  await vm.runInNewContext(fs.readFileSync(script, "utf8"), sandbox);
  process.stdout.write(JSON.stringify({ closed }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            harness,
            str(SCRIPTS / "dogfood_report_issue_prefill.js"),
            scenario,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == exit_code, result.stderr
    assert json.loads(result.stdout) == {"closed": True}


@pytest.mark.unit
async def test_user_count_preserves_output_without_duplicate_query(monkeypatch, capsys):
    namespace = runpy.run_path(str(SCRIPTS / "count_users.py"))
    count_users = namespace["count_users"]
    result = MagicMock()
    result.first.return_value = (3, 2, 4, 5)
    connection = AsyncMock()
    connection.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__aenter__.return_value = connection
    engine.dispose = AsyncMock()
    monkeypatch.setitem(
        count_users.__globals__, "create_async_engine", MagicMock(return_value=engine)
    )
    monkeypatch.setitem(
        count_users.__globals__,
        "subprocess",
        SimpleNamespace(
            run=MagicMock(return_value=SimpleNamespace(stdout="local-only"))
        ),
    )
    monkeypatch.setenv("DATABASE_HOST", "127.0.0.1")

    await count_users()

    assert capsys.readouterr().out.splitlines() == [
        "Total users: 3",
        "Users with GitHub: 3",
        "Users with attempts: 2",
        "Total attempts: 4",
        "Total steps completed: 5",
    ]
    assert "github_username IS NOT NULL" not in str(
        connection.execute.call_args.args[0]
    )
    engine.dispose.assert_awaited_once()
