# Copilot Instructions

## Branching

Always work on a feature branch. Never commit directly to `main`, never stage or edit files while on `main`.

**Before making any file changes**, make sure you git pull to ensure your local branch is up to date, and verify you are on a feature branch:

```bash
git branch --show-current
```

If the output is `main`, stop and create a branch first. This includes editing files, running formatters, or any operation that modifies the working tree.

Use descriptive prefixes:

- `fix/` for bug fixes (e.g., `fix/deterministic-pr-grading`)
- `feat/` for new features (e.g., `feat/phase4-verification`)
- `chore/` for maintenance, deps, docs (e.g., `chore/update-dependencies`)
- `refactor/` for code restructuring (e.g., `refactor/auth-middleware`)

Workflow:

1. Check current branch before doing anything
2. Create a branch from `main` if not already on one
3. Make changes, commit, and push to the branch
4. Open a Pull Request to merge into `main`
5. Never force-push to `main` or commit directly to it

After a PR merges (or auto-merges), git may switch you back to `main`. Always re-check your branch before starting the next task.

## Code Comments and Docstrings

Keep docstrings short and useful. One line is enough for most functions.

- Don't restate the function name or parameters when they're obvious
- Don't document implementation history ("removed X", "no longer uses Y")
- Don't add `Args:` / `Returns:` blocks when the types and names are self-explanatory
- Only comment code that needs clarification — skip the obvious

## No Hacks or Bandaids

Never write hacks, bandaids, or workarounds. Specifically:

- Don't silence linters, type checkers, or tests just to make a warning go away. If a rule fires, either the code is wrong (fix the code) or the rule doesn't fit the codebase (have an explicit, justified discussion before excluding it).
- Don't paper over a symptom when a proper fix exists. If the proper fix requires a refactor, surface that choice explicitly: name the refactor, explain why the band-aid is tempting, and let the user decide.
- Don't add `# noqa`, `# type: ignore`, `try/except: pass`, or rule exclusions to make CI green. Same applies to inserting "make the warning happy" code that wouldn't otherwise belong.
- When you catch yourself reaching for one of these, stop and propose the proper fix as a real choice instead.

## Database Migrations

Never edit alembic migration files after they've been created. They are immutable historical records that may have already run in production. If a migration needs correcting, create a new migration instead.

When a migration updates row values AND modifies check constraints, always drop the constraints first, then update rows, then add new constraints. Postgres enforces check constraints during the UPDATE, so updating rows before dropping the old constraint will fail if the new value isn't in the old constraint's allowed list.

When a migration adds a unique index or unique constraint, always clean up existing rows that would violate it first in the same migration. Production databases have data that CI's empty test database does not. Delete or merge duplicate rows before creating the constraint.

## Infrastructure and Terraform Changes

For infrastructure changes, always review the Terraform plan for deployment permissions and Azure resources that may already exist.

- Run an Azure-backed `terraform plan` before merging infrastructure changes.
- Check whether the GitHub Actions deployment identity can create every resource in the plan. Normal Azure RBAC is not enough for Microsoft Graph or Entra app registration resources.
- Be careful with new provider families, especially `azuread`. Adding `azuread_*` resources usually means the deploy identity needs Microsoft Graph permissions, or the identity object should be pre-created and passed into Terraform.
- For Azure child config resources that Azure creates by default, update or import the existing resource instead of trying to create it. For Function App authentication, use `azapi_update_resource` for `authsettingsV2`.
- For risky auth or identity changes, prefer the smallest safe platform change first, then deploy application code after the platform gate is confirmed.

## Docker in the devcontainer

This devcontainer uses **Docker outside of Docker**, not Docker-in-Docker. The
Docker CLI runs inside the container, but it talks to the Docker daemon on your
host machine through a forwarded socket. There is no nested Docker daemon.

- **Before saying Docker is unavailable, run the preflight check:**
  `scripts/check-docker.sh`. It confirms the Docker CLI is installed and can
  reach the host daemon, and it prints clear next steps if it cannot. Do not
  stop a task with "Docker is not available here" without running this first.
- If the preflight fails, the usual fix is to make sure Docker is running on the
  host and then rebuild the devcontainer (Command Palette: "Dev Containers:
  Rebuild Container").
- **Builds work normally**: `docker build -f api/Dockerfile ... .` reads the
  build context from inside the container and streams it to the host daemon.
- **Bind mounts need host paths**: because the daemon runs on the host, a bind
  mount like `docker run -v /workspaces/...:/x` will not find the container's
  path on the host. Use the `LOCAL_WORKSPACE_FOLDER` environment variable (set
  in `devcontainer.json`) for the repo root instead of `/workspaces/learn-to-cloud-app`.

## Quality Gates

This project uses [poethepoet](https://poethepoet.natn.io/) (poe) as the single
source of truth for the quality-gate commands. The tasks live in the root
`pyproject.toml` and run across the whole uv workspace.

Do not push unless `uv run poe check` passes. It runs two steps:

- `uv run poe static`: ruff lint, ruff format check, ty type check, and the
  migration SQL safety lint, across the whole workspace.
- `uv run poe test`: every test suite with its coverage gate, plus the
  verification Functions import smoke test.

Continuous integration runs the exact same `uv run poe` tasks, so a green
`uv run poe check` locally means the same checks will pass in CI.

Do not write `# noqa`, `type: ignore`, or ty/ruff suppression comments unless absolutely unavoidable.

### Validation Workflow (run continuously, not just at the end)

`uv run poe static` runs the prek hooks with `--all-files`. prek only inspects
files that git is already tracking, so a brand-new file you have not staged yet
is silently skipped. Keep that one blind spot in mind:

1. **After every batch of edits**, run `uv run poe static` (or the full `uv run poe check`). It takes seconds and covers every project at once.
2. **When you create a new file**, `git add` it first so the hooks can see it, or run ruff and ty directly against the file path: `uv run ruff check path/to/new_file.py`.
3. **Before declaring work complete**, run the full `uv run poe check` and treat any failure as blocking.
4. **Write code that respects ruff and ty by default**: match `line-length = 88`, prefer explicit imports, keep functions type-annotated, avoid unused imports and variables. Don't write code first and clean up later; getting it right the first time is faster.
5. **Long SQL or string literals in migrations** must respect `line-length = 88`. Break long `SELECT` / `INSERT` lists across multiple lines inside the SQL string, because ruff lints the Python source, not the SQL.

If a check fails, fix it before moving on. Do not batch lint fixes for the end of the task.

## Communication

When talking to @madebygps, use verbose, plain-language explanations. Explain what changed, why it matters, what the tradeoffs are, and what should happen next. Do not assume technical shorthand is obvious.

Write in clear, plain language. Avoid jargon, technical shorthand, and dense descriptions. PR titles, commit messages, code comments, and explanations should all be easy to understand at a glance. If a non-engineer wouldn't understand it, rewrite it simpler.

## Search Hygiene

Keep search output small and targeted.

- Start broad searches with file names or counts, not full content output.
- Use narrow paths, glob filters, and result limits before switching to matching lines.
- If a search result is too large, do not read the saved bulk output first. Narrow the query, path, or file type and search again.
- Once target files are known, read specific line ranges instead of whole large files.

## Research

When asked to research, or if you need to research something that is Azure related, use the azure-skills plugin. For everything else, use firecrawl or tavily (whichever one is installed) and/or context7.

**Do not use the built-in web search tool.** It is not an acceptable fallback. If firecrawl, tavily, and context7 are all unavailable, say so and ask the user how to proceed rather than silently falling back to web search.
