---
applyTo: "**/*"
---

# General Repository Instructions

## Git & Commits

### Pre-Commit (MANDATORY)
```bash
pre-commit run --all-files
```
- **NEVER** use `--no-verify` to bypass
- **NEVER** use `SKIP=ty` or skip any pre-commit hooks
- **NEVER** commit if pre-commit fails—fix all issues first

### Conventional Commits
Format: `type(scope): description`

| Type | Use For |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `refactor` | Code restructure |
| `test` | Adding tests |
| `chore` | Deps, config |

Scopes: `api`, `frontend`, `infra`, `content`, `skills`

## Comments

### Remove These
- **Obvious/redundant** — restates what code clearly does
- **Commented-out code** — delete it, don't comment it
- **Vague TODOs** — must have context: `TODO(#123): Handle rate limit`
- **Change logs** — version control handles this

### Keep These
- **Why comments** — explain intent/reasoning
- **Non-obvious behavior** — gotchas, edge cases
- **Workarounds** — with justification and removal date
- **Warnings** — `WARNING:` or `SECURITY:`
