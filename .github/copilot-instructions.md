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

GitHub evaluates stacked PR workflow filters against the stack base, so `pull_request.branches: [main]` runs CI for every PR in a stack targeting `main`.

## Stacked PRs

Split a large, tightly-coupled change into a chain of small PRs when reviewers benefit from seeing it in stages. Use the `gh-stack` extension (installed) and its skill at `.agents/skills/gh-stack/SKILL.md` to create and sync the stack. Do not hand-manage rebases.

Rules:

1. Chain off `main`: bottom PR base = `main`, each higher PR base = the branch below it. Only stack work that genuinely depends on the branch below; independent work gets its own top-level branch off `main`.
2. Merge through GitHub's native Stack controls. Merging a PR lands it and every unmerged PR below it together; do not merge those PRs individually.
3. Prefer **Squash and merge** for one commit per PR. GitHub handles the remaining stack's retargeting and cascading rebase after a full or partial stack merge.
4. Identify deployment boundaries before merging. Merge only through the highest layer that can deploy safely, wait for that deployment when required, then merge the remaining layer.
5. Active `main` deployments are never canceled. Back-to-back merges retain the running deployment and only the newest pending deployment, while stale PR runs still cancel.


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
