"""Regression coverage for local and operational script cleanup."""

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scenario", "exit_code"),
    [("success", 0), ("failed_checks", 2), ("exception", 1)],
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
    const issue = new URL("https://github.com/example/project/issues/new");
    issue.searchParams.set("title", dashboard ? "Dashboard Issue" : "Issue with topic");
    issue.searchParams.set("labels", "content");
    issue.searchParams.set("body", scenario === "failed_checks" ? "" : [
      "**Page:** " + currentUrl,
      "**Title:** Example",
      "**When:** Now",
      "## Environment",
      "Browser: Test",
      dashboard ? "page=dashboard" : "**Context:** phase=1, topic=test-topic"
    ].join("\\n"));
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
