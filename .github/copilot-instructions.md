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

- Default to short, plain, direct output. Answer in the fewest words that fully address what was asked.
- Skip filler, hedging, and pleasantries ("happy to help", "sure!", "let me just...").
- No structural padding for short answers: no headers, no bold labels, no scaffolding, no 'in short' or 'to summarize', just answer the question directly.
- Answering a question is not permission to be verbose. Lead with the direct concise answer. Add detail only if asked for additional context or explanation.
- Don't teach or give multiple framings unless asked.

## Pull Request Descriptions

- Write PR descriptions in plain language.
- Concisely describe the change, why it is needed, and what effect it has.
- Lead with what changes, why it is needed, and what effect it has.
- Avoid unexplained jargon. If a technical term is necessary, define it immediately with a concrete explanation.
- Describe rollout states plainly. For example, say "the alert is evaluated but sends no notifications" instead of relying on "shadow mode."

## Research

If you need to research something that is Azure related always use the azure-skills plugin.
