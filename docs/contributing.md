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
| Local verification submissions | Node.js 20+, npm, Azure Functions Core Tools 4 |
| Terraform and Azure operations | Terraform 1.5.x, Azure CLI, GitHub CLI |
| Production database investigation | Azure CLI, PostgreSQL client |
| Dog-food browser testing | Node.js 20+, npm, Playwright MCP and Chromium |
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
docker compose up -d db azurite dts aspire-dashboard
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

#### Frontend and verification worker

Install Node.js 20 or newer using the
[official Node.js installation instructions](https://nodejs.org/en/download).
Then install frontend dependencies and Azure Functions Core Tools:

```bash
cd api && npm ci && cd ..
npm install -g azure-functions-core-tools@4 --unsafe-perm true

node --version
npm --version
func --version
```

Node.js is only required for Tailwind CSS changes and local Functions
development. The API and Python test suites do not require it.

Create the Functions-local environment before starting Core Tools:

```bash
UV_PROJECT_ENVIRONMENT="$PWD/apps/verification-functions/.venv" \
  uv sync --project apps/verification-functions --locked
```

The Functions environment is intentionally separate from the workspace root
environment. Python 3.13 uses this project-local environment to isolate
application packages such as `protobuf` and `grpcio` from the worker's bundled
dependencies. The VS Code Functions task creates and refreshes it automatically.

#### Azure and Terraform

Install the Azure CLI using Microsoft's
[WSL/Linux instructions](https://learn.microsoft.com/cli/azure/install-azure-cli-linux)
and Terraform using HashiCorp's
[Linux instructions](https://developer.hashicorp.com/terraform/install).
Install GitHub CLI using its
[Linux instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)
if `gh` is not already available.
Infrastructure work should use Terraform 1.5.x to match CI.

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
npm install -g @playwright/mcp@latest
playwright-mcp install-browser chromium --with-deps
```

The root `.mcp.json` also defines optional Context7, Tavily, Azure, and Aspire
servers. Install them only when using those Copilot integrations:

```bash
npm install -g \
  @upstash/context7-mcp@latest \
  tavily-mcp@latest \
  @azure/mcp@latest
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

# Test suites (with coverage gates) plus the verification import smoke test.
uv run poe test

# Everything above, in order. Run this before opening a pull request.
uv run poe check
```

Continuous integration runs the exact same `uv run poe` tasks, so a green
`uv run poe check` locally means the same checks will pass in CI.

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
5. **Authenticate** via a signed session cookie (no real GitHub OAuth needed)
6. **Test authenticated pages** — Dashboard, Account, Phase, Topic
7. **Toggle a learning step** checkbox and verify it persists
8. **Report results** as a structured summary with pass/fail for each page

### Prerequisites

Install the Playwright MCP server and Chromium before the first run:

```bash
npm install -g @playwright/mcp@latest
playwright-mcp install-browser chromium --with-deps
```

The MCP server is configured in `.mcp.json` for the Copilot CLI and
`.vscode/mcp.json` for VS Code. The database must contain at least one user;
`scripts/dogfood_session.py` creates the local authenticated session.

### Cross-architecture support

The agent runs on both x86_64 and ARM64 Linux because it uses **Chromium**, not
the `chrome` channel. Google Chrome has no ARM64 Linux build, and pointing the
MCP server at it there fails at launch.

Two things must stay in sync, so change them together:

- The `--browser chromium` arg in `.mcp.json` and `.vscode/mcp.json`.
- The documented `playwright-mcp install-browser chromium` setup command.

Install the browser through `playwright-mcp`, not a separately installed
`playwright` CLI. The MCP server bundles its own playwright-core and resolves a
specific browser revision; a standalone CLI may install a different one, and the
MCP server then reports the browser as not installed.

### Artifacts

Screenshots are saved to `.dogfood/` (gitignored). No artifacts pollute the repo.

### How it works under the hood

| Component | File |
|-----------|------|
| Agent instructions | `.github/agents/dog-food.agent.md` |
| MCP server config | `.mcp.json`, `.vscode/mcp.json` |
| Session cookie generator | `scripts/dogfood_session.py` |
| Chromium + MCP install | `playwright-mcp install-browser chromium --with-deps` |

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

### Authentication and sessions

GitHub OAuth establishes a signed client-side session cookie containing
`user_id` and `github_username`. Session middleware verifies its signature and
age on subsequent requests; those requests do not contact GitHub again.
The cookie is signed, not encrypted, so do not store secrets in its payload.

OAuth issuance and session reads share `validate_identity` from
`learn_to_cloud.core.auth`. It requires:

- An integer GitHub ID from 1 through `2**63 - 1`. Booleans, floats, numeric
  strings, zero, negative values, and larger integers are rejected, not converted.
- A username string of 1 through 255 characters containing non-whitespace text,
  representable as UTF-8 and containing no NUL character. The length is the
  existing database capacity, not a GitHub naming rule.

GitHub's authenticated profile response establishes account identity. We do not
duplicate signup rules, check reserved names, or requery GitHub on each request.
Session reads preserve accepted values without trimming or changing case.
OAuth retains lowercase normalization and validates the normalized value before
database access, since lowercasing can increase a Unicode string's length.
The returned database identity must match that validated identity, and the
transaction must commit before a new cookie identity is written. A mismatch
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
warning. Names must never enter logs, spans, metric labels, browser identity
context, or session cookies.

The callback scopes database error sanitization to its profile transaction,
including commit and session cleanup. An engine `handle_error` listener registered
before SQLAlchemy instrumentation sanitizes the asyncpg dialect's DBAPI error
arguments and chains, preserving the driver error type and SQLSTATE for cleanup.
It returns a fixed message and a bounded SQLAlchemy error category. This prevents
dependency spans from exporting driver detail before the callback can catch it.
The callback then raises a value-free error without the driver exception chain;
the normal 500 handler and failed request telemetry still run, no new session is
issued, and session cleanup retains rollback ownership. Other transactions and
non-database exceptions keep their existing handling. Engine parameter hiding
also prevents bound values in SQL logs; it alone cannot hide driver diagnostics.

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
INSERT/ON CONFLICT/RETURNING statement. In contrast, `get_or_create` returns
an existing user's profile unchanged.

#### Session reads

Missing both identity fields is normal anonymous access, including a session
containing only OAuth state. Partial or malformed identity is also treated as
anonymous, but both identity fields are removed from the existing session object.
Unrelated entries, including OAuth state, are preserved. Middleware persists the
cleaned cookie or expires it if nothing remains.

Rejecting numeric-string IDs is an intentional change from the previous
coercing reader. Valid sessions remain valid; rejected sessions require login
again. Local tools such as `scripts/dogfood_session.py` must also supply valid
identity values. No migration, backfill, or cookie-key rotation is needed.
Malformed cookie encoding, JSON, or top-level session shapes are a separate
middleware concern tracked in
[#834](https://github.com/learntocloud/learn-to-cloud-app/issues/834).

The API uses one identity type:

| Name | Purpose |
|------|---------|
| `AuthenticatedUser` | Plain identity data: numeric user ID and GitHub username. Use it in helpers receiving an existing identity. |
| `CurrentUser` | An `Annotated` alias that tells FastAPI to call `require_authenticated_user` and supply that identity to a protected route. |
| `OptionalCurrentUser` | Supplies the same identity or `None` to a public route. |

Import these from `learn_to_cloud.core.auth`. Routes access
`current_user.user_id` or `current_user.github_username`; do not introduce
ID-only dependencies or a separate browser-user type.
`require_authenticated_user` raises `AuthenticationRequired` when the session
has no complete identity. It does not choose a browser redirect or check
whether the application account still exists. Account-validity work is tracked
in [#829](https://github.com/learntocloud/learn-to-cloud-app/issues/829).

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

POST `/auth/logout` needs no authenticated dependency. It clears the session,
explicitly expires the browser cookie, and returns 303 to `/`, including when
the cookie is missing, rejected, or already cleared. Explicit cookie deletion
also handles rejected cookies that middleware presents as an empty session.
The signed session lifetime is currently 30 days. Logout removes this browser's
cookie but does not revoke a previously copied valid cookie; session-revocation
and expiry guarantees are tracked in
[#828](https://github.com/learntocloud/learn-to-cloud-app/issues/828).

Auth behavior is covered through real routes, session middleware, and HTTP
redirects in `api/tests/routes/test_auth_http.py`. Auth overrides are useful
for unrelated rendering tests, but must not replace authentication in tests
of the auth contract itself. Request telemetry records handled 401/303 outcomes;
it must not add usernames, user IDs, cookie values, or session identifiers.
Handled identity rejection emits a bounded warning without exception details;
ordinary anonymous access does not. Failed OAuth attempts do not clear an
existing valid login or unrelated authorization state.
See the [telemetry schema](observability/telemetry-schema.html).

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
packaged YAML under
`packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/phases/`.
To change it:

1. Edit the YAML files. CI compiles them into the packaged curriculum artifact.
2. Validate locally:
   ```bash
   cd packages/learn-to-cloud-shared
   uv run python scripts/validate_content.py
   ```
3. Open a PR. CI runs the same validators.

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
[documentation root](https://learntocloud.github.io/learn-to-cloud-app/) and
[presentation](https://learntocloud.github.io/learn-to-cloud-app/scaling-with-github/).
