# Copilot Instructions

## Branching

Never edit, commit, or stage directly to `main`.

Check the current branch before doing anything. If on `main`, create a branch
using `fix/` for bug fixes, `feat/` for features, `chore/` for maintenance or
docs, or `refactor/` for restructuring.

Commit, push, and open a pull request only when requested. Use the `ship-it`
skill for the delivery workflow. Merging requires explicit authorization.
Never force-push to `main`; report Git errors rather than rewriting history.

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

Run targeted checks during development. `uv run poe check` must pass before
pushing, no exceptions. Run additional checks when changing their inputs.
Task definitions live in `pyproject.toml`; see
[Quality Gates](../docs/contributing.md#quality-gates) for check selection and
API smoke testing.

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
