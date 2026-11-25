# Copilot Instructions

## Project

Learn to Cloud is a Python FastAPI app. It serves Jinja2 templates with HTMX,
Alpine.js, and Tailwind CSS v4. PostgreSQL stores learner state. Curriculum
content is YAML in `src/learn_to_cloud/content/`.

- Source code is in `src/learn_to_cloud/`. Tests mirror it in `tests/`.
- [Where changes belong](../docs/architecture.md#where-changes-belong) says
  which package owns each kind of change.
- [Guides by task](../docs/contributing.md#guides-by-task) links the guide for
  each subsystem. Read the matching guide before you change that subsystem.

## How to Work

- Start with a targeted search when possible. Broaden the search or survey the
  codebase when needed.
- Do not silence linters, type checkers, or tests to make them pass.
- If an attachment or tool output is missing, say so. Do not guess its contents.
- For Azure research, use the azure-skills plugin.

## Code Style

- Write code that explains itself. Comment only what needs clarification.
- Keep docstrings to one line unless more is necessary. Do not restate names,
  parameters, or change history.

## Verification

- Run the smallest check that covers your change while you work.
- `uv run poe check` must pass before you push.
- See [Quality Gates](../docs/contributing.md#quality-gates) for which checks
  to run and how to smoke test the API.

## Git and Pull Requests

- Never edit, stage, commit, or force-push to `main`. If you are on `main`,
  create a branch with a `fix/`, `feat/`, `chore/`, or `refactor/` prefix.
- Commit, push, and open a pull request only when asked. Use the `ship-it`
  skill. Merge only with explicit approval.
- Report Git errors. Do not rewrite history to work around them.
- Write PR descriptions in plain language: what changed, why, and its effect.
  Define any necessary technical term in plain words.

## Communication

- Be short and direct. Answer in the fewest words that fully answer the
  question.
- Skip filler, pleasantries, and summary padding.
- Add detail or teaching only when asked.
