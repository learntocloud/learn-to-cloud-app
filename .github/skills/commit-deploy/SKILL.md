---
name: commit-deploy
description: Commit changes and monitor the deploy workflow. Use when pushing code and wanting to watch CI/CD status in real-time.
---

# Commit & Deploy

## Workflow

### Step 1: Run pre-commit (REQUIRED)

**Always run pre-commit locally before committing.** Do not proceed until it passes.

```bash
pre-commit run --all-files
```

If pre-commit fails:
- Review the output to see which hooks failed
- Many hooks auto-fix files (ruff, prettier) - check `git diff` for changes
- Re-run `pre-commit run --all-files` until all hooks pass
- Only then proceed to commit

### Step 2: Stage and commit

```bash
git add -A
git commit -m "type(scope): description"
```

### Step 3: Push

```bash
git push
```

### Step 4: Watch deploy workflow

```bash
gh run list --workflow=deploy.yml --limit 1
gh run watch <run-id>
```

## Conventional Commit Types

| Type | Use For |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `refactor` | Code restructure |
| `test` | Adding tests |
| `chore` | Deps, config, maintenance |

**Scopes:** `api`, `frontend`, `infra`, `content`, `skills`

## If CI Fails

```bash
gh run view <run-id> --log-failed
```

Then use `cicd-debug` skill to diagnose.
