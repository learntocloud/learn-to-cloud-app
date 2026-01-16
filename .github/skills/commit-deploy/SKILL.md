---
name: commit-deploy
description: Commit changes and monitor the deploy workflow. Use when pushing code and wanting to watch CI/CD status in real-time.
---

# Commit & Deploy

## Workflow

```bash
# 1. Run pre-commit
pre-commit run --all-files

# 2. Stage and commit (use conventional commits)
git add -A
git commit -m "type(scope): description"

# 3. Push
git push

# 4. Watch deploy workflow
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
