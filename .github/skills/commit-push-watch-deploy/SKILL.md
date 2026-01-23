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

**CRITICAL RULES:**
- **NEVER use `--no-verify`** to bypass pre-commit
- **NEVER commit if pre-commit fails** - fix all issues first
- If a hook fails, fix it. Don't skip it.

If pre-commit fails:
1. Review the output to see which hooks failed
2. Many hooks auto-fix files (ruff, prettier) - check `git diff` for changes
3. Fix any issues that weren't auto-fixed
4. Re-run `pre-commit run --all-files` until **ALL hooks pass**
5. Only then proceed to commit

**Expected passing hooks (all must show "Passed"):**
- `trim trailing whitespace`
- `fix end of files`
- `check yaml/json`
- `ruff` (Python lint)
- `ruff-format` (Python format)
- `ty type check` (Python types)
- `pytest tests` (may skip if no DB - that's OK)
- `ESLint` (Frontend lint)
- `TypeScript Check` (Frontend types)
- `vitest unit tests` (Frontend tests)

### Step 2: Stage and commit

```bash
git add -A
git commit -m "type(scope): description"
```

**Note:** Pre-commit runs again on commit. If it fails here, you missed something in Step 1.

### Step 3: Push

```bash
git push
```

### Step 4: Watch deploy workflow

```bash
gh run list --workflow=deploy.yml --limit 1
gh run watch <run-id>
```

Wait for the workflow to complete. Do not assume success.

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
