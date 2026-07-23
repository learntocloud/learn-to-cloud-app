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

`uv run poe check` must pass before pushing, no exceptions. Run it after every batch of edits, not just at the end. See the `validate` and `ship-it` skills for the exact commands and steps.

## Communication

Default to short, plain, direct output. Answer in the fewest words that fully address what was asked.

- Skip filler, hedging, and pleasantries ("happy to help", "sure!", "let me just...").
- Don't recap the full plan before or after doing it. State only what changed, and only if it's not obvious from a diff.
- Use plain language over jargon, but plain does not mean long. A short plain sentence beats a long plain paragraph.
- Don't narrate routine, successful steps ("ran tests, they passed"). Elaborate only when something is surprising, risky, or needs a decision from @madebygps.
- Answering a question is not license to be verbose. Lead with the direct answer in 1-3 sentences. Add detail only if needed for correctness. Don't teach, list every option, or give multiple framings unless asked.
- No structural padding for short answers: no headers, no bold labels, no "here's why / here's the tradeoff" scaffolding unless the answer genuinely needs sections.
- Give one recommendation, not a menu, unless @madebygps asks to compare options.
- Exceptions (may be longer): security-sensitive or irreversible changes, tradeoffs affecting a decision, or when explicitly asked to explain in depth or "walk me through" something.

## Research

If you need to research something that is Azure related always use the azure-skills plugin.
