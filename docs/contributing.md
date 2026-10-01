# Contributing Guide

## Development Setup

Development runs directly in WSL or Linux. See the
[README Quick Start](https://github.com/learntocloud/learn-to-cloud-app#quick-start)
for setup instructions.

### Tooling by workflow

Install only the tools needed for the work you plan to do.

| Workflow | Required tools |
|----------|----------------|
| API, tests, and quality gates | Git, Docker with Compose, `uv`, Node.js 20+ |
| Frontend CSS changes | npm and frontend dependencies |
| Local verification submissions | API environment and PostgreSQL |
| Terraform and Azure operations | Terraform matching CI, Azure CLI, GitHub CLI |
| Production database investigation | Azure CLI, PostgreSQL client |
| Dog-food browser testing | `uv`, Playwright Python API and Chromium |
| Optional Copilot MCP integrations | Aspire CLI and the configured npm MCP servers |

See the [Maintainer Guide](maintainer-guide.md) for infrastructure and optional
Copilot tooling, and [Testing](testing.md#dog-food-agent-ai-powered-qa) for
browser testing setup.

`uv` installs the required Python runtime; a matching system Python installation
is not required. Install [Node.js](https://nodejs.org/en/download) before running
the full test suite.

### Core setup

Follow the README Quick Start for installation, local dependencies,
environment configuration, migrations, and starting the API. Docker Desktop
users must enable WSL integration for their distribution.
Then install the repository hook and check the environment:

```bash
scripts/check-docker.sh
uv run prek install
uv run poe check
```

### Frontend

Install frontend build dependencies from the repository root:

```bash
npm ci
```

Local verification uses the API environment; there is no separate worker host.

## Quality Gates

This project uses [poethepoet](https://poethepoet.natn.io/) as the single source
of truth for quality-gate commands. The tasks are defined in the root
`pyproject.toml`.

Use targeted checks during development; the full `uv run poe check` gate must
pass before pushing. New files must be staged for the static checks to inspect
them; stage only files belonging to the current task.

```bash
# Static checks: ruff lint, ruff format, ty type check, migration lints,
# curriculum content validation, and generated schema/curriculum drift.
# This runs the prek hooks against every file in the repository.
uv run poe static

# Test suites with coverage gates.
uv run poe test

# Static checks, installed-package smoke testing, and tests.
# Run this before pushing.
uv run poe check
```

Continuous integration runs `uv run poe check`, plus the curriculum version
check against the base commit and path-selected Terraform checks. Run those
additional checks when changing their inputs.

For workflow changes that add a Python command, also run that exact command
with only the environment variables supplied by the workflow. Do not rely on
local-only environment settings.

See [Testing](testing.md) for targeted commands, fixture conventions, and
guidance on callable contracts.

### API smoke testing

After Python application changes, start a fresh API process on `127.0.0.1:8000`.
Require HTTP 200 from `/health`, `/ready` once dependencies are ready, and
`/openapi.json`; the OpenAPI response must also be valid JSON.
Track the exact process ID and terminate that process during cleanup, never
unrelated listeners. Report startup logs if an endpoint fails.

## Conventions

Keep request-serving database and network I/O asynchronous. Follow the owning
module's types and helpers rather than introducing parallel conventions.
Schema changes must remain compatible with the application still serving
traffic; see [Database migrations](migrations.md).

## Guides by task

| Task | Guide |
|------|-------|
| Change routes, rendering, or verification | [Architecture](architecture.md) |
| Change login, profiles, or sessions | [Authentication and sessions](authentication.md) |
| Add logs, spans, or application events | [Telemetry](telemetry.md) |
| Write tests, run browser QA, or reset local submissions | [Testing](testing.md) |
| Change the database schema | [Database migrations](migrations.md) |
| Edit phases, topics, steps, or requirements | [Editing curriculum](curriculum.md#editing-curriculum) |
| Understand learner progress and completion | [Progression system](progression-system.md) |
| Configure issue triage, Copilot tools, or documentation maintenance | [Maintainer Guide](maintainer-guide.md) |
| Investigate production alerts | [Alert runbook](runbooks/alerts.md) |

Keep general contribution workflow in this guide. Put subsystem contracts in
their owning guides and operational procedures in runbooks; link rather than
duplicate instructions. Add new guides to the [documentation index](index.md).
Document decisions, non-obvious guarantees, and actionable procedures. Keep
function inventories, configurable defaults, and implementation history in
source, tests, and version control instead of duplicating them here.
