# Testing

See [Quality Gates](contributing.html#quality-gates) for workspace checks and
API smoke testing. Node.js is required for browser-contract tests even when
running them through pytest.

## Targeted checks

Run each command from the repository root:

```bash
# Lint the application and shared runtime.
uv run --project api ruff check api packages/learn-to-cloud-shared

# Select the relevant suite, file, or test.
uv run --project api pytest api/tests/ -m unit
uv run --project api pytest api/tests/ -m integration
uv run --project packages/learn-to-cloud-shared pytest packages/learn-to-cloud-shared/tests/
```

Mark tests as `unit` or `integration`; use `pytest_asyncio.fixture` for async
fixtures. Application database fixtures use rollback isolation. Migration
tests instead recreate a dedicated disposable database; see
[Database migrations](migrations.html#migration-tests).

## Test code and callable contracts

Keep suite-specific fakes in `tests/fakes/` and fixtures in `conftest.py`.
Helpers shared across suites belong in
[`learn-to-cloud-shared-test-support`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/packages/learn-to-cloud-shared-test-support),
as a dev dependency only. Do not ship test helpers in runtime dependencies.

Before removing unused arguments or `async`, trace callers, dependency injection,
callbacks, and mocks. A fixture argument may provide essential setup. Use
`usefixtures` when only setup is needed; do not add dummy argument uses or awaits
to satisfy a lint rule.

The package `pyproject.toml` files document reviewed callback exceptions:
[`API`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/pyproject.toml)
and
[`shared runtime`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/pyproject.toml).
Review new code in exempted files manually; expanding exceptions needs a
caller/contract review and maintainer agreement.

## Dog Food Agent (AI-Powered QA)

Give `@dog-food` a concrete learner goal, such as completing a phase or submitting
a requirement. It explores that flow, uses a coverage backstop, and reports
defects and friction with server-side evidence; it is not a fixed page checklist.
The
[`agent instructions`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/agents/dog-food.agent.md)
own the procedure and required inputs.

Start with a working local API environment and an existing local account.
Install the Python browser separately from any MCP browser:

```bash
uv run --with playwright playwright install chromium
```

Use Chromium on both x86_64 and ARM64 Linux. The local session helper refuses
production targets and does not invent a fallback user. Its output is a
credential: pass it directly to browser automation, never logs, issues, or commits.
Capture server logs, report what was not exercised, and clean up only processes
started for the run. Artifacts belong in gitignored `.dogfood/`.

## Resetting local verification submissions

From `api/`, run the reset script interactively, or scope and preview the reset:

```bash
uv run python scripts/reset_local_submissions.py --user-id 6733686 --requirement-slug devops-implementation --dry-run
```

For automation or agent-driven resets, summarize the matched users, requirements,
and outcomes and obtain explicit confirmation. Then repeat the same filters with
`--yes` instead of `--dry-run`. Without those flags, the script previews matches
and asks for confirmation.

Both filters are repeatable. Without filters, the reset covers every current
curriculum requirement and local user. The
[`script`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/scripts/reset_local_submissions.py)
resolves slugs through the curriculum artifact and deletes matching attempts.
It refuses non-local databases; never bypass this guard or substitute ad-hoc SQL.
