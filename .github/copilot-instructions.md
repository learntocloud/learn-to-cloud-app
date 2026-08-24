# Copilot Instructions

## Branching

Never edit, commit, or stage directly to `main`.

Workflow:

1. Check current branch before doing anything
2. Create a branch from `main` if not already on one
  - `fix/` for bug fixes (e.g., `fix/deterministic-pr-grading`)
  - `feat/` for new features (e.g., `feat/phase4-verification`)
  - `chore/` for maintenance, deps, docs (e.g., `chore/update-dependencies`)
  - `refactor/` for code restructuring (e.g., `refactor/auth-middleware`)
3. Make changes, commit, and push to the branch
4. Open a Pull Request to merge into `main`
5. Never force-push to `main`, alert user if some git error occurs

## Stacked PRs

Use stacked PRs only when a large, tightly-coupled change benefits from staged review. Use the `gh-stack` extension and its skill at `.agents/skills/gh-stack/SKILL.md` for stack mechanics.

Repository policy:

1. Independent work gets a standalone branch from `main`; only stack work that genuinely depends on the layer below it.
2. Prefer **Squash and merge** so each PR lands as one commit.
3. Identify deployment boundaries before merging. Merge only through the highest layer that can deploy safely, wait for that deployment when required, then merge the remaining layer.


## Code Comments and Docstrings

Keep docstrings short and useful. One line is enough for most functions.

- Don't restate the function name or parameters when they're obvious
- Don't document implementation history ("removed X", "no longer uses Y")
- Don't add `Args:` / `Returns:` blocks when the types and names are self-explanatory
- Only comment code that needs clarification — skip the obvious

## No Hacks or Bandaids

- Don't silence linters, type checkers, or tests just to make a warning go away. If a rule fires, either the code is wrong (fix the code) or the rule doesn't fit the codebase (have an explicit, justified discussion before excluding it).
- Don't add `# noqa`, `# type: ignore`, `try/except: pass`, or rule exclusions to make CI green. Same applies to inserting "make the warning happy" code that wouldn't otherwise belong.
- If a real fix would require a bigger refactor, don't quietly patch around the symptom instead. Tell the user and let them choose.

## Docker in WSL

- **Before saying Docker is unavailable, run the preflight check:**
  `scripts/check-docker.sh`. It confirms the Docker CLI is installed and can
  reach the daemon, and it prints clear next steps if it cannot. Do not
  stop a task with "Docker is not available here" without running this first.
- If the preflight fails under WSL, make sure Docker Desktop is running and WSL
  integration is enabled for the current distribution.
- Local processes reach Compose services through their published loopback ports,
  such as PostgreSQL at `127.0.0.1:55432`. Compose services reach each other by
  service name, such as `db:5432`.

## Quality Gates

`uv run poe check` must pass before pushing, no exceptions. Run it after every batch of edits, not just at the end. See the `validate` and `ship-it` skills for the exact commands and steps.

## Communication

- Default to short, plain, direct output. Answer in the fewest words that fully address what was asked.
- Skip filler, hedging, and pleasantries ("happy to help", "sure!", "let me just...").
- No structural padding for short answers: no headers, no bold labels, no scaffolding, no 'in short' or 'to summarize', just answer the question directly.
- Answering a question is not permission to be verbose. Lead with the direct concise answer. Add detail only if asked for additional context or explanation.
- Don't teach or give multiple framings unless asked.

## Pull Request Descriptions

- Write PR descriptions in plain language that a learner can understand.
- Lead with what changes, why it is needed, and what effect it has.
- Avoid unexplained jargon. If a technical term is necessary, define it immediately with a concrete explanation.
- Describe rollout states plainly. For example, say "the alert is evaluated but sends no notifications" instead of relying on "shadow mode."

## Research

If you need to research something that is Azure related always use the azure-skills plugin.
