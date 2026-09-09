# Contributing Guide

## Development Setup

Development runs directly in WSL or Linux. See the
[README Quick Start](https://github.com/learntocloud/learn-to-cloud-app#quick-start)
for setup instructions.

### Tooling by workflow

Install only the tools needed for the work you plan to do.

| Workflow | Required tools |
|----------|----------------|
| API, shared package, tests, and quality gates | Git, Docker with Compose, `uv` |
| Frontend CSS changes | Node.js 20+, npm |
| Local verification submissions | API environment and PostgreSQL |
| Terraform and Azure operations | Terraform 1.16.1 (matching CI), Azure CLI, GitHub CLI |
| Production database investigation | Azure CLI, PostgreSQL client |
| Dog-food browser testing | `uv`, Playwright Python API and Chromium |
| Optional Copilot MCP integrations | Aspire CLI and the configured npm MCP servers |

`uv` installs and selects Python 3.13 from `api/.python-version`; a matching
system Python installation is not required.

### Core setup

Docker Desktop users must enable WSL integration for their Linux distribution.
Confirm Docker is reachable before continuing:

```bash
scripts/check-docker.sh
```

Install `uv` if needed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install the workspace and configure the repository's pre-commit hook:

```bash
uv sync --all-packages --locked
uv run prek install
cp api/.env.example api/.env
docker compose up -d db aspire-dashboard
cd api && uv run alembic upgrade head && cd ..
```

Verify the core environment:

```bash
uv --version
uv run python --version
docker compose version
uv run poe check
```

### Resetting local verification submissions

From `api/`, preview and reset every local verification attempt:

```bash
uv run python scripts/reset_local_submissions.py
```

The script shows the matching attempts and asks for confirmation before
deleting them. To limit the reset to one GitHub user ID:

```bash
uv run python scripts/reset_local_submissions.py --user-id 6733686
```

For automation, preview first and pass `--yes` only after confirming the
matches:

```bash
uv run python scripts/reset_local_submissions.py --dry-run
uv run python scripts/reset_local_submissions.py --yes
```

### Optional toolsets

#### Frontend

Install Node.js 20 or newer using the
[official Node.js installation instructions](https://nodejs.org/en/download).
Then install frontend dependencies:

```bash
cd api && npm ci && cd ..

node --version
npm --version
```

Node.js is needed for Tailwind CSS changes and browser telemetry contract tests.
Local verification uses the API environment; there is no separate worker host.

The verification UI uses server-rendered states, not simulated check progress.
Completed polling responses carry `X-Verification-Complete` so `verification.js`
can refresh the workspace, including unlocks and history, without a full reload.
The response retains a reload fallback when that enhancement is unavailable.
Keep the checking message and animation preserved between polls with
`hx-preserve`; animate only changed states and respect reduced-motion preferences.
The rendering tests include Node-based transition contracts.

#### Azure and Terraform

Install the Azure CLI using Microsoft's
[WSL/Linux instructions](https://learn.microsoft.com/cli/azure/install-azure-cli-linux)
and Terraform using HashiCorp's
[Linux instructions](https://developer.hashicorp.com/terraform/install).
Install GitHub CLI using its
[Linux instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)
if `gh` is not already available.
Infrastructure work should use Terraform 1.16.1 to match CI and the `~> 1.16`
constraint in `infra/provider.tf`.

```bash
az login
az account show --output table
terraform version
gh auth status
```

Install local command-line utilities used by production investigation skills:

```bash
sudo apt update
sudo apt install -y jq postgresql-client

jq --version
psql --version
```

Azure CLI, Terraform, `jq`, and `psql` are not required for normal API
development. They are required for infrastructure plans, deployment
diagnostics, Azure-backed verification, and production database queries.

#### Copilot and browser tooling

Install the browser tooling used by the dog-food agent:

```bash
uv run --with playwright playwright install chromium
```

The root `.mcp.json` also defines optional Context7, Tavily, Azure, Aspire, and
Playwright servers. Install them only when using those Copilot integrations:

```bash
npm install -g \
  @upstash/context7-mcp@latest \
  tavily-mcp@latest \
  @azure/mcp@latest \
  @playwright/mcp@latest
playwright-mcp install-browser chromium --with-deps
curl -sSL https://aspire.dev/install.sh | bash
```

## Quality Gates

This project uses [poethepoet](https://poethepoet.natn.io/) as the single source
of truth for quality-gate commands. The tasks are defined in the root
`pyproject.toml` and run across the whole uv workspace.

```bash
# Static checks: ruff lint, ruff format, ty type check, migration SQL lint.
# This runs the prek hooks against every file in the workspace.
uv run poe static

# Test suites with coverage gates.
uv run poe test

# Static checks, installed-package smoke testing, and tests.
# Run this before opening a pull request.
uv run poe check
```

Continuous integration runs the same `uv run poe` tasks, plus curriculum
artifact/schema checks, migration checks, and path-selected Terraform checks.
Run those additional checks when changing their inputs.

### Running checks against a single project

When you only want to lint or test one member, you can still call the tools
directly from that member's directory:

```bash
# Lint just the API and shared package
cd api && uv run ruff check . ../packages/learn-to-cloud-shared

# Run just the API tests
cd api && uv run pytest tests/
uv run pytest tests/ -m unit
uv run pytest tests/ -m integration

# Run just the shared package tests
cd packages/learn-to-cloud-shared && uv run pytest tests/
```

- Tests use transactional rollback for isolation, with no table recreation per test
- Mark tests with `@pytest.mark.unit` or `@pytest.mark.integration`
- Async fixtures use `@pytest_asyncio.fixture`

### Unused arguments and async interfaces

Ruff enforces `ARG001` and the explicitly selected preview rule `RUF029` across
the API, shared runtime, and shared test-support packages, including tests.
Trace callers, dependency declarations, callback registration, and mocks before
removing an argument or `async`. A fixture argument may create required data;
use its returned value when the test needs that data, or a test-level
`usefixtures` mark when only setup is needed. Remove setup with no consumer.
An `AsyncMock` side effect need not be async unless its own body awaits work.

The reviewed exceptions below preserve actual callable contracts, not dead code.
Paths are relative to the named package.

| Package and files | Rules | Contract |
| --- | --- | --- |
| API: `src/learn_to_cloud/main.py` | `ARG001` | Starlette passes `(request, exc)` to the fixed 404 response handler. |
| API: `tests/core/test_middleware.py` | Both | ASGI supplies scope/receive/send and awaits application and send/receive callbacks. |
| API: `tests/services/test_dashboard_service.py`, `tests/test_migration_chain.py` | `ARG001` | SQLAlchemy supplies six event arguments; these listeners inspect emitted SQL. |
| Shared: `src/learn_to_cloud_shared/core/observability.py` | `RUF029` | HTTPX instrumentation requires and awaits the async sanitization hook. |
| Shared: `src/learn_to_cloud_shared/verification/checks/career.py`, `src/learn_to_cloud_shared/verification/checks/tokens.py` | `RUF029` | The engine awaits every check, including local checks that finish immediately. |
| Shared: `tests/verification/test_engine.py` | Both | Named async fakes exercise exception frames, execution order, and evidence propagation; some do not inspect their context. |
| Shared: `tests/repositories/test_user_repository.py` | `ARG001` | Flush/SQL listeners receive metadata beyond the specific state or statement being observed. |
| Shared: `tests/verification/test_github_http.py`, `tests/verification/test_repo_files.py` | `ARG001` | HTTPX passes a request even when a fake response depends only on attempt count or a fixed failure. |

These exceptions apply to entire files, so review new code in those files for
the exempted rules manually. All other rules still apply. Do not add artificial
awaits, dummy argument uses, or renamed parameters to make warnings disappear.
Changes to this exception scope require another caller/contract review and
maintainer agreement; tests are not exempt as a category.

### Test-only code

Keep suite-specific fakes under that suite's `tests/fakes/` and fixtures in its
`conftest.py`. The shared verification tests follow this pattern for repository
files, branch references, workflow runs, and GitHub metadata. Production modules
keep the interfaces and real adapters, not their test implementations.

Helpers used by multiple workspace test suites live in
`packages/learn-to-cloud-shared-test-support`, imported as
`learn_to_cloud_shared_test_support`. Requirement factories and settings-cache
reset helpers are shared this way. Each consuming member declares this package
in its `dev` dependency group, so the normal `uv run pytest tests/` command from
that member installs it automatically. Production installs and exports use
`--no-dev`; do not add test support to runtime dependencies or re-export it from
the application package.

`RepoFiles` is a static interface: its fake accepts the same owner, repository,
and branch arguments even though it reads one configured snapshot. Keep those
argument names for keyword-call compatibility. Runtime `isinstance` checks
against this protocol are not supported.

Deployment integrity commands, authenticated smoke endpoints, and curriculum
authoring utilities remain operational code even when they also help tests.

## Dog Food Agent (AI-Powered QA)

The project includes a **dog-food agent** — an AI-powered QA workflow that automatically starts the local API, opens a headless browser, and walks through every page checking for errors, broken UI, and console messages.

### How to run it

In VS Code Copilot Chat, type:

```
test our app
```

or invoke the agent directly with `@dog-food`. The agent will:

1. **Start the API** on port 8000 and verify `/health` + `/ready`
2. **Install Chromium** if needed (headless, `--no-sandbox`)
3. **Test all public pages** — Home, Curriculum, FAQ, Privacy, Terms, Status
4. **Toggle dark mode** and verify it works
5. **Authenticate** via a persisted local session (no real GitHub OAuth needed)
6. **Test authenticated pages** — Dashboard, Account, Phase, Topic
7. **Toggle a learning step** checkbox and verify it persists
8. **Report results** as a structured summary with pass/fail for each page

### Prerequisites

Install Chromium for the agent's Playwright Python API before the first run:

```bash
uv run --with playwright playwright install chromium
```

The agent runs browser scripts with `uv run --with playwright python`.
The database must contain at least one user;
`scripts/dogfood_session.py` commits an authenticated session for an existing
local account. It requires development settings and a loopback database and
refuses production targets. Missing accounts and database errors are failures,
not reasons to invent a user. Its cookie JSON is a local credential: pass it
directly to browser automation, never into logs, issue reports, or commits.

### Cross-architecture support

The agent runs on both x86_64 and ARM64 Linux because it uses **Chromium**, not
the `chrome` channel. Google Chrome has no ARM64 Linux build, and pointing the
MCP server at it there fails at launch.

For optional browser use through the MCP servers in `.mcp.json` and
`.vscode/mcp.json`, install Chromium through
`playwright-mcp install-browser chromium`. That server uses a different
Playwright distribution; its browser installation is separate from the
dog-food agent's Python API.

### Artifacts

Screenshots are saved to `.dogfood/` (gitignored). No artifacts pollute the repo.

### How it works under the hood

| Component | File |
|-----------|------|
| Agent instructions | `.github/agents/dog-food.agent.md` |
| Session cookie generator | `scripts/dogfood_session.py` |
| Chromium install | `uv run --with playwright playwright install chromium` |

## Copilot Skills

The project ships several Copilot agent skills in `.github/skills/`:

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `validate` | "validate" | Run the quality gate and smoke-test the API |
| `ship-it` | "ship it" | Validate, commit, push, and open a PR |
| `check-prod` | "check prod" | Assess Azure production health |
| `debug-deploy` | "debug deploy" | Diagnose deployment failures |
| `query-prod-db` | "query prod db" | Query production PostgreSQL safely |
| `reset-local-submissions` | "reset local submissions" | Reset local verification attempts |
| `reset-prod-submissions` | "reset prod submissions" | Reset production verification attempts |
| `review-pr-comments` | "review PR comments" | Triage and address PR feedback |
| `review-terraform` | "review terraform" | Review Terraform safety and permissions |
| `plan-terraform` | "plan terraform PR" | Plan an infrastructure PR against remote state |
| `write-migration` | "write migration" | Create production-safe Alembic migrations |

## Architecture

```
Routes (HTTP) → Services (Business Logic) → Repositories (Database)
```

- **Routes** handle HTTP concerns, dependency injection, and template rendering
- **Services** contain business rules — no HTTP knowledge
- **Repositories** execute queries — return ORM models or primitives

### Rendering ownership

Routes and services delegate template-data preparation to
`api/src/learn_to_cloud/rendering/`. These helpers are synchronous and do not
perform database or network I/O.

| Module | Responsibility |
|--------|----------------|
| `requirement_cards.py` | Card states, builders, and card-specific display properties |
| `verification_forms.py` | Form display models and their builder |
| `feedback.py` | Feedback formatting, safe evidence links, and incomplete-verification wording shared by cards and history |
| `progress.py` | Progress bars and phase-topic progress |
| `topic_navigation.py` | Previous/next topic links |
| `page_content.py` | FAQ content and community/help links |

The top-level `learn_to_cloud/verification_forms.py` owns submission checking,
input shapes, action URLs, and shared length limits. Form rendering uses that
contract rather than duplicating its rules. Keep related display models and
builders together, and import them directly from their owning modules.

### Background verification

The API lifespan starts one sequential verification loop per process. PostgreSQL
stores the pending work; atomic claims prevent two replicas from executing the
same attempt. Execution is a plain async function with a timeout, not a workflow
engine. There are no workflow retries, checkpoints, external queues, or
verification jobs. Existing provider-level retry policies remain separate.

Overdue cleanup detects both attempts waiting too long for a claim and executions
that outlive their limit, then saves a terminal outcome. A process crash does not
resume its execution; cleanup lets the learner submit again. Production keeps
one API replica available and allows at most two, without changing CPU or memory.

`verification_worker` settings default to a 5-second poll interval, 180-second
execution timeout, 600-second queue timeout, and 10-second shutdown timeout.
These are worker limits, separate from provider SDK timeouts.

For the migration cutover, stop the old verification host **before** running
`0062_api_verification_worker`. That migration marks all active attempts as
`server_error` with cause `verification_interrupted` and adds the pending-work
index. Then start the API worker. It claims only attempts with no `started_at`;
there is no replay, lease, or checkpoint migration.

During this rollout, Terraform retains two inert legacy startup settings so the
previous API image can still start before its replacement arrives. The new
worker ignores them; they do not connect to the stopped verification host.

Rendering preserves the distinction between failed learner work and incomplete
verification. Operational logs and spans stay at the existing request/service
boundaries; browser telemetry context remains in `core/templates.py`.

### Verification checks and workflows

The shared package separates workflow configuration from execution:

| Module under `verification/` | Responsibility |
| --- | --- |
| `core.py` | Typed check callables, steps, results, contexts, and workflows. |
| `checks/` | Focused adapters around domain validators and evidence collectors. |
| `workflows.py` | Ordered steps, username requirements, and rubric configuration per submission type. |
| `engine.py` | Ownership preflight, execution, evidence flow, aggregation, step tracing, and grading preparation. |
| `execution.py` | Persisted message/result projection, not the engine core. |

To add a check, define a public async function in a focused check module and
reference it directly from a `Step` in `workflows.py`. Every step callable
accepts a `StepContext` and returns a `StepResult`. Bind configuration such as
rubric tasks with `functools.partial` and typed keyword-only arguments.
Give each step a stable `name` for telemetry and a `task_id`; the engine calls
`await step.check(context)` without a check registry or dispatch-only params.
Extend the check and workflow tests, including the fixed workflow contracts.
Importing the workflows fully initializes them; no startup registration call
or required check import order is needed.

Keep execution and step telemetry in the engine. Provider error classification
stays in domain helpers; domain validators do not depend on engine contracts.
Import extracted symbols from their owning modules, not through `engine.py`.
The worker's `engine.run_verification` entry point is unchanged.

### Repository verification ownership

The worker calls `run_verification` in the shared verification engine for every
assignment. Before repository-based checks run, one shared preflight compares
GitHub's repository `owner.id` with the trusted numeric learner ID loaded from
the attempt. It uses the attempt's saved username, not a browser-supplied owner
ID or a separate current-username lookup.

Wrong ownership, a missing repository, or a private repository stops grading
with learner-facing feedback. If the learner changed their GitHub username,
they should sign out, sign in again, and submit a new attempt. GitHub access,
rate-limit, network, and malformed-response failures leave verification
incomplete rather than failing the assignment.

A valid same-owner redirect supplies one canonical execution target to the
existing checks, evidence collectors, and rubric prompt. Original submitted
values and historical completions remain unchanged. Ownership is checked once
before verification, not continuously; this does not provide an atomic GitHub
snapshot or commit-consistent evidence. Direct checker helpers assume the
shared engine has performed this preflight.

### Verification errors and incomplete attempts

`verification/errors.py` owns only shared retry primitives and the data-only
`UpstreamResponseError` (safe message, response status, optional retry delay).
GitHub response classification and telemetry belong to `github_errors.py`;
deployed-API and GHCR errors stay in their respective integration modules.
Native HTTPX request failures remain request failures, with no invented status.
Integrations that retry explicitly select their errors, never the common base.

GitHub network and non-404 HTTP failures leave an attempt incomplete, not failed
learner work. Failed evidence fetches stop collection and prevent all grading,
including tasks collected earlier in the run. History and current cards retain
the saved safe cause, explain that the work was not judged to have failed, and
provide retry and issue-reporting guidance. Old rows without a cause use an
outcome-based explanation rather than assuming an outage.

A GitHub 404 before presence is established retains its missing/private-resource
meaning. Proven missing required work is completed learner feedback; optional
files proven absent are allowed. A selected file disappearing after discovery
instead leaves verification incomplete. Truncated GitHub trees cannot establish
absence or complete selection.

GitHub API GET/HEAD and GHCR retain three attempts for their existing transient
errors; raw-file reads make one attempt per file. Learner-API creation and AI
analysis each make one request, with no automatic retries. Deployed-API failures
keep their existing completed learner-failure behavior; transient GHCR failures
remain incomplete. Response-status telemetry never includes provider bodies,
headers, tokens, repository links, or learner endpoint URLs.

Unexpected check or ownership-preflight exceptions still propagate. Their
`verification.step` span records `verification.step.result=error`, class-only
`error.type`, and ERROR status, never an exception message or stack trace.
Automatic exception recording and status descriptions stay disabled.
Cancellation is not converted into an error result. Expected provider failures
keep their existing bounded classifications; ordinary learner failures do not
mark the step span as a service error.

### Complete grading evidence

Each rubric receives one complete, bounded packet for its published submission
contract. `EvidencePolicy` owns required paths, optional named files, and limits.
All selected files, including present optional
bonus evidence, are collected in full or no grading request is made. Selection
never drops files by sort order or priority, truncates content, summarizes code,
or chases imports. Phases 3 and 5 use deterministic CI checks; they do not
collect repository source or request LLM grading.
The final prompt boundary validates task/source identity, selected paths,
required groups, optional presence, full-content hashes, counts, byte totals,
and truncation flags on the in-process evidence packet.

| Phase | Evidence contract | Files / item / total limits |
| --- | --- | --- |
| 6 | Required `.github/workflows/codeql.yml`; optional `.github/dependabot.yml` for bonus review. | 3 / 50 KiB / 75 KiB |
| 7 | Complete submitted text as `career-reflection.md`, preserving the empty-text gate; no GitHub reads. | 1 / 20 KiB / 20 KiB |

Supporting files aid interpretation but do not authorize inference about
uncollected code or a whole-repository credential review.
Completeness is relative to this documented contract, not arbitrary layouts
or a commit-atomic snapshot.

Evidence failures use existing `verification_attempts.error_code`; no new
outcome, schema migration, or historical rewrite is needed. Closed reasons:

| Reason | Outcome and recovery |
| --- | --- |
| `evidence.required_missing` | Completed learner failure naming the published missing work; no LLM call. |
| `evidence.changed` | Incomplete retrieval/state change; retry later or after the repository stops changing. |
| `evidence.file_limit` | Selected file count exceeds the service limit. |
| `evidence.item_limit` | One complete item's UTF-8 bytes exceed the service limit. |
| `evidence.total_limit` | Combined complete UTF-8 content exceeds the service limit. |
| `evidence.selection` | The packet cannot satisfy its resolved evidence contract. |
| `evidence.configuration` | Missing target or contradictory evidence configuration. |

Budget, selection, and configuration failures are non-counting service errors:
the work was not judged, and unchanged retries may not help. Learners should
report the issue, not shrink or split valid work. Cards and history use the
persisted bounded cause, never message parsing, and show no partial rubric
score or failed-rubric badge. Unknown historical codes retain the generic
incomplete explanation. Existing upstream and LLM error categories and
precedence remain intact.

Evidence assembly emits one `verification.evidence.assembled` event per decision
with exactly these attributes:

| Attribute | Allowed values |
| --- | --- |
| `evidence.outcome` | `complete`, `required_missing`, `retrieval_failed`, `incomplete` |
| `evidence.reason` | `complete`, `retrieval`, or one of the seven `evidence.*` reasons above |
| `evidence.selected_count` | Numeric count of selected items |
| `evidence.collected_count` | Numeric count of fully collected items |
| `evidence.total_bytes` | Numeric total of collected UTF-8 content bytes |

It supplements `verification.step`
and the canonical `verification.attempt.completed` event's
`verification.error.code`; it is not a second attempt-completion event.
Evidence telemetry must never include code, submitted text, content hashes,
repository URLs, arbitrary paths, or learner identities. Do not add attempt
IDs or learner data as metric dimensions. Existing attempt correlation is
unchanged. See the [alert runbook](runbooks/alerts.md#incomplete-grading-evidence)
for recovery; no automatic retries or historical regrading are implied.

### Deployed API verification

The Phase 4 deployment check makes two requests: `POST /entries`, then
`POST /entries/{id}/analyze`. Creation must return 200 or 201 and a non-empty
string ID, either in the response object or its `entry` object. Analysis must
return 200 with the matching `entry_id`, a supported sentiment, a non-empty
summary, and a non-empty list of topic strings. No GET, listing check, nonce,
journal-field validation, or historical-data audit is involved.

Each step runs once, including on network errors and 5xx responses. Creation
failure stops before analysis; a missing ID is reported rather than recovered
with a GET. Analysis has a 30-second timeout. Feedback identifies the failed
step, including actionable instructions for an unimplemented analysis endpoint
(501). Success confirms entry creation and analysis, not ownership or listing
behavior. The check remains deterministic and does not request grading.

Created entries stay in the learner's journal even if analysis fails. The entry
records "Submitted deployed API for verification.", describes checking entry
creation and AI analysis, and sets the intention to review the result and address
reported issues. It does not claim verification passed. The verifier never
deletes or updates entries; learners can keep or remove them themselves.

#### Findings and boundaries (#855)

The [original workflow][deployed-api-original-workflow] combined ownership
challenges, ID recovery, retries, and deletion with creation and analysis.
The [original historical-entry filter and validation][deployed-api-original-history]
also expanded a deployment probe into a partial stored-data audit. None of that
is required by the two-request flow, so it has been removed rather than split
into more modules.

The [request boundary][deployed-api-original-http] remains necessary: connection
pooling, timeouts, HTTPS, disabled redirects, and private-target checks protect
our server while it requests a learner-supplied URL. Base-path normalization and
absent-peer-metadata behavior are unchanged. Response-peer inspection occurs
after a request and cannot undo its side effects.

Safe timeout, server-error, request-error, and target-block diagnostics remain.
Success records `verification.deployed_api.verified` and
`verification.deployed_api.ai_verified`; challenge and cleanup diagnostics are
not emitted. Diagnostics exclude URLs, entry IDs, bodies, headers, and raw
exception messages. Programming errors and cancellation propagate.

[deployed-api-original-http]: https://github.com/learntocloud/learn-to-cloud-app/blob/a070cfe9f8537e0a4d475f5933417ed6b9ba13c8/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/deployed_api.py#L111-L249
[deployed-api-original-workflow]: https://github.com/learntocloud/learn-to-cloud-app/blob/a070cfe9f8537e0a4d475f5933417ed6b9ba13c8/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/deployed_api.py#L423-L828
[deployed-api-original-history]: https://github.com/learntocloud/learn-to-cloud-app/blob/a070cfe9f8537e0a4d475f5933417ed6b9ba13c8/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/verification/deployed_api.py#L662-L692

### Authentication and sessions

GitHub OAuth establishes an opaque login cookie, `ltc_session`, backed by
PostgreSQL. The cookie is a random credential, not an encoded identity. The
`auth_sessions` table stores only its SHA-256 digest, account ID, and creation,
update, last-activity, and absolute-expiry timestamps. It stores no IP address,
User-Agent, device label, profile snapshot, or OAuth token. Normal authenticated
requests resolve the current account from this store; they do not contact GitHub.

The separate signed `session` cookie is only for Authlib's temporary OAuth
handshake state, with a ten-minute browser lifetime. Its contents are signed,
not encrypted. Unrelated in-flight OAuth state survives callback failures;
OAuth responses cannot replace the separate authentication cookie.
Both cookies use HttpOnly, SameSite=Lax, Path=/, no Domain, and Secure in
production. Browser expiry is not the authority for session validity.

OAuth issuance uses `validate_identity` from `learn_to_cloud.core.auth`.
It requires:

- An integer GitHub ID from 1 through `2**63 - 1`. Booleans, floats, numeric
  strings, zero, negative values, and larger integers are rejected, not converted.
- A username string of 1 through 255 characters containing non-whitespace text,
  representable as UTF-8 and containing no NUL character. The length is the
  existing database capacity, not a GitHub naming rule.

GitHub's authenticated profile response establishes account identity. We do not
duplicate signup rules, check reserved names, or requery GitHub on each request.
OAuth retains lowercase normalization and validates the normalized value before
database access, since lowercasing can increase a Unicode string's length.
The returned database identity must match that validated identity, and the
account upsert and session-creation transaction must commit before a new cookie
or successful-login event is issued. A mismatch
is an internal error, not an ordinary rejected login.

#### Profile names

The numeric GitHub ID is the durable account key. Username and optional
`display_name` are presentation data refreshed from GitHub at each login.
Nonblank names are preserved exactly, including Unicode and outer/repeated
whitespace; they are not split or truncated. Missing, null, or whitespace-only
names become SQL `NULL`. The dashboard falls back to the username and escapes
all names as ordinary text. Normal HTML may visually collapse whitespace.
Community profiles continue to expose only username and avatar.

Non-string names, NUL characters, and unpaired Unicode surrogates are ignored
with the fixed value-free warning `auth.callback.display_name_ignored`. Login
continues normally; this is not rejected identity. Blank names produce no
warning. Do not deliberately log profile payloads or add names to span
attributes, metric labels, browser identity context, or session cookies.

Profile persistence uses normal database exception handling. Failed writes or
commits still roll back, return the generic 500 response, and issue no new
session. Engine parameter hiding keeps bound values out of SQL logs and
formatted SQLAlchemy errors, but database diagnostics can still include public
GitHub profile values. This is an accepted diagnostic tradeoff; we do not
rewrite driver exceptions or guarantee profile-value redaction. OAuth tokens,
credentials, cookies, and session secrets must remain out of telemetry.

The internal `GET /api/user/me` response replaces `first_name` and `last_name`
with `display_name` without API versioning. All other fields remain unchanged:

```json
{"id":42,"github_username":"learner","display_name":"  李  ","avatar_url":null,"is_admin":false,"created_at":"2024-01-01T00:00:00Z"}
```

`UserRepository.upsert` flushes **all pending work in the current session** before
its profile statement. It refreshes an already-loaded user in place; provider
profile arguments override pending profile edits, while unrelated changes
survive. Passing `None` explicitly clears the name/avatar. It does not commit:
the caller owns commit/rollback for both flush and upsert, and flush failures
propagate before the profile statement. A clean session still uses one
INSERT/ON CONFLICT/RETURNING statement.

#### Session reads

Missing authentication cookies and OAuth-state-only cookies are anonymous
without a session/account query. Legacy identity fields are never trusted and
are removed while preserving unrelated OAuth state. The cutover requires
everyone to sign in again; there is no legacy fallback or session backfill.
The signing key does not need rotation.

Resolution is asynchronous and cached for this request only, including
anonymous results. A valid session is conditionally touched using the database
clock and returned with its current account in a short committed transaction.
Pages, `/api/user/me`, and HTMX step rendering reuse that account rather than
select it again. No session lock or database connection remains held during
template rendering, provider calls, or verification work.

Unknown, revoked, deleted-account, and expired credentials cannot authenticate
or recreate rows. Supplied invalid credentials are cleared on handled responses,
including 401s and redirects. A database failure is a real service failure,
not anonymous access or permission to trust a cookie. Responses affected by
identity vary on Cookie; authenticated and account/auth responses are private
and non-cacheable. Static asset caching is unchanged.

| Session limit | Behavior |
| --- | --- |
| Inactivity | Reject at seven days since the last authenticated request. Pages, APIs, and verification polling count; static assets, health probes, and simply keeping a page open do not. |
| Absolute lifetime | Reject at thirty days after creation, even with continual activity. A new GitHub login starts a new lifetime. |
| Expired-row retention | A successful login prunes at most 100 idle- or absolute-expired rows. No worker or wall-clock removal deadline is promised; pending cleanup never makes expired rows valid. |

`SessionConfig` exposes `idle_timeout_seconds` (604800),
`absolute_timeout_seconds` (2592000), and `oauth_state_max_age_seconds` (600).
These are positive durations, and inactivity cannot exceed absolute lifetime.
Seven inactive days is a convenience tradeoff, not a claim of high-assurance
session timeout policy.

Choose the dependency for the data the route actually consumes:

| Name | Purpose |
|------|---------|
| `AuthenticatedUser` | Plain identity data: numeric user ID and GitHub username. Use it in helpers receiving an existing identity. |
| `CurrentUser` | An `Annotated` alias that tells FastAPI to call `require_authenticated_user` and supply that identity to a protected route. |
| `CurrentAccount` | Supplies the loaded `User` account to a protected route that needs profile fields or renders account-aware templates. |
| `OptionalCurrentAccount` | Supplies that loaded account or `None` to a public route. |

Import these from `learn_to_cloud.core.auth`. Identity consumers access
`current_user.user_id` or `current_user.github_username`; account consumers access
`account.id`, `account.github_username`, and loaded profile fields. Do not introduce
ID-only dependencies or a separate browser-user type. Pass accounts explicitly
to templates and rendering helpers; do not look them up through `request.state`.

All three aliases share `optional_authenticated_account`, which resolves the
session and loads the account in one short, committed transaction before route
work. FastAPI caches this shared subdependency per request; a request-local cache
also prevents repeat resolution and touches when the resolver is called directly.
The cached account is the only request-state identity; consumers receive the
account or immutable identity through dependencies. Database failures propagate
rather than becoming anonymous requests.
`require_authenticated_account` raises `AuthenticationRequired` when no live
session and current account resolve; the required identity dependency derives
from it. Neither chooses a browser redirect.

The injected account is a read-only, loaded ORM snapshot, not a transaction.
Session makers use `expire_on_commit=False` so loaded scalar fields remain
available after the authentication session closes. Do not lazy-load relationships,
attach the snapshot for writes, or mutate it. Use an explicit service and database
session for additional reads or writes; do not query the account again just to
render it.

Browser navigation is a route policy, separate from identity loading.
Page routers select `LoginRedirectRoute` from `learn_to_cloud.core.routing`
using `APIRouter(route_class=LoginRedirectRoute, ...)`. That route class uses
FastAPI's supported route-handler extension and catches only
`AuthenticationRequired`; unrelated errors keep their normal behavior.

| Unauthenticated request | Response |
|-------------------------|----------|
| JSON API endpoint | 401, without a login redirect |
| HTMX endpoint, with or without `HX-Request` | 401, without a login redirect |
| Protected page navigation | 303 to `/auth/login` |
| Protected page requested with `HX-Request: true` | 401; the existing frontend handler navigates to login |

A browser mutation that intentionally redirects uses 303 so the next request
is GET, not a replay of POST or DELETE. Do not infer auth response policy from
URL prefixes or `Accept` headers.

POST `/auth/logout` needs no authenticated dependency. It deletes this browser's
session, commits, clears its cookies, and returns 303 to `/`. Replaying an exact
copy of that cookie fails across all app processes; independent browser sessions
stay valid. Missing, malformed, unknown, expired, and already-revoked cookies
retain repeatable cleanup behavior. If the database cannot confirm revocation,
the route fails instead of claiming success.

The Account page's Sign out everywhere form posts to `/auth/logout-all`. It
requires a live session and a session-bound, non-bearer CSRF token. Missing or
incorrect tokens return 403 without deletion. The form asks for confirmation,
includes this browser, and disables HTMX boost so its 303 navigates normally.
The server locks the account before rechecking the requesting session and
deleting all current sessions. Login issuance uses the same account-first lock
order; a genuinely later GitHub login can create a new session.

Both account-deletion endpoints commit account deletion and foreign-key
cascades before reporting success, emitting `user.account_deleted`, or clearing
cookies. All sessions, progress, and submissions are removed atomically.
Other browsers become anonymous on their next request. A new login can recreate
the same numeric GitHub account ID, but never revives an old session.

Revocation takes effect when its transaction commits. Already-authorized work
may finish, and running verification work is not cancelled. An expired open
page is rejected on its next server interaction; there is no background logout
timer. Sign out everywhere revokes this app's sessions, not GitHub sessions or
GitHub authorization. After cookie theft, sign in on a trusted browser and use
that action. A compromised GitHub account must also be secured at GitHub.

Auth behavior is covered through real routes, session middleware, and HTTP
redirects in `api/tests/routes/test_auth_http.py`, with persisted multi-browser
lifecycle coverage in `api/tests/routes/test_session_lifecycle.py`.
Auth overrides are useful
for unrelated rendering tests, but must not replace authentication in tests
of the auth contract itself. Request telemetry records handled 401/303 outcomes;
it must not add usernames, user IDs, cookie values, or session identifiers.
Session rejections use bounded reasons without exception details; expected
expiry, unknown-session, and cutover outcomes are informational, not automatic
compromise warnings. Ordinary anonymous access emits no event. Failed OAuth attempts do not clear an
existing valid login or unrelated authorization state.
See [Telemetry](#telemetry).

### Telemetry

Use OpenTelemetry/Application Insights for requests, dependencies, timing,
correlation and unexpected exception diagnostics. Add application events for
meaningful actions and saved outcomes, not another copy of every SDK signal.
There is no global field registry: keep fields useful and review them with the
code. Preserve event names and fields used by alerts. Unique attempt IDs belong
in logs/traces, not metric dimensions.

Telemetry explains what happened; the database holds submitted values and
feedback. Investigate using the operation ID and `verification.attempt.id`,
then look up the database record when authorized. Not every fetched file or
grading prompt is stored there; some failures need reproduction. Do not
deliberately attach credentials, cookies, submitted bodies, evidence, or model
prompts/results to logs or spans. SQL parameter hiding and small URL filters
remain because OAuth/polling query values are credentials the SDK does not
automatically remove. Normal paths and native exception details are useful;
we do not guarantee redaction of public profile values or arbitrary error text.

The browser SDK collects dependencies and errors without cookies or browser
storage. Two HTMX hooks record page views because SDK history tracking counts
HTMX's `replaceState` and `pushState` twice. Do not enable both approaches.
Provider error classification still controls learner feedback and incomplete
verification; it is not a reason to suppress unrelated programming errors.

Azure Monitor owns FastAPI instrumentation in production. Local OTLP configures
the same instrumentation explicitly with SDK defaults. Keep the default ASGI
receive/send spans rather than replacing Azure Monitor's setup just to reduce
trace noise.

HTTP requests and background verification share the `learn-to-cloud-api` role,
Azure Monitor pipeline in production, and local OTLP pipeline in Aspire.
`verification.attempt.created` records accepted work;
`verification.attempt.started` and the `verification.execute` span mark a claimed
attempt. `verification.attempt.completed` is emitted only after the final outcome
is saved. `verification.llm_grading.failed` retains bounded `error.type` categories;
never attach prompts, evidence, fetched source, or credentials.

`verification.attempt.stuck` includes `verification.attempt.age_seconds` and
`verification.stuck.reason` (`queued_beyond_limit` or `execution_beyond_limit`).
Fatal loop failures emit `verification.worker.failed` with only `error.type`,
then re-raise; they do not emit raw exception details or the HTTP-only
`unhandled.exception`. Both `/health` and `/ready` return 503 when the worker
task has finished. Shutdown cancels the worker and closes the grader's clients.
The existing stuck alert covers overdue work and worker failures; final-outcome
and LLM alerts remain separate.

## Conventions

- Async/await everywhere -- no sync database calls
- Database models use `TimestampMixin` for `created_at`/`updated_at`
- Enums: `class MyEnum(str, PyEnum)` with `native_enum=False` in columns
- Config via `pydantic-settings` (`Settings` class in `core/config.py`)
- Production migrations run through an Azure Container Apps Job before API deployment

## Database Migrations

### Combine compatible schema and application changes

An additive migration and the app code that uses it can ship in one PR.
Deployment runs migrations and checks schema agreement before updating the
API; a migration failure stops that update. Keep model metadata aligned with
the migrated schema, and apply migrations before starting the new code locally.

The old app continues running while migrations execute, so it must still work
with the expanded schema. For example, add `display_name` and start using it
in the same release, but retain the legacy name columns for old instances and
rollback. Remove unused columns in a later cleanup after those instances have
retired.

Brief downtime is acceptable for this app; separate schema-only releases are
not required just to avoid it. For incompatible changes, explicitly plan to
stop affected app instances before migrating, or use compatible intermediate
steps. The deployment workflow does not stop old instances before migrations.
Never drop data or weaken migration failure checks merely to combine releases.

See [Database Migrations](migrations.html) for more on how migrations work.

## Editing curriculum content

Curriculum (phases, topics, steps, hands-on requirements) lives in
source-only YAML under
`packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/phases/`.
To change it:

1. Edit the YAML files.
2. Validate locally:
   ```bash
   cd packages/learn-to-cloud-shared
   uv run python scripts/validate_content.py
   uv run python scripts/compile_curriculum.py
   uv run python scripts/generate_yaml_schemas.py
   ```
3. Commit the YAML, compiled artifact, and any generated schema changes, then
   open a PR. CI runs the validators and rejects generated-file drift.

See [Curriculum Architecture](curriculum.html) for the full packaged-artifact
architecture.

## GitHub Pages

Repository documentation is published from `docs/` at
`https://learntocloud.github.io/learn-to-cloud-app/`. The Pages workflow:

1. Builds the Markdown and static HTML with Jekyll.
2. Deploys the generated site to the `github-pages` environment.

Pull requests build the site without deploying it. Merges to `main` that touch
the docs or the Pages workflow publish automatically. Maintainers can
also use the workflow's **Run workflow** action for a manual publish.

Repository settings must keep **Pages > Build and deployment > Source** set to
**GitHub Actions**. After publishing, verify the
[documentation root](https://learntocloud.github.io/learn-to-cloud-app/).
