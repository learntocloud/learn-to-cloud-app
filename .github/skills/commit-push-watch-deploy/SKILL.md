---
name: commit-deploy
description: Commit changes and monitor the deploy workflow. Use when pushing code and wanting to watch CI/CD status in real-time.
---

# Commit & Deploy

> **Note**: Pre-commit and conventional commit standards are documented in `.github/instructions/git.instructions.md`. This skill provides the **deploy monitoring workflow**.

## Workflow

### Step 1: Run pre-commit (REQUIRED)

**Always run pre-commit locally before committing.** Do not proceed until it passes.

```bash
pre-commit run --all-files
```

See `.github/instructions/python.instructions.md` for pre-commit rules.

### Step 2: Stage and commit

```bash
git add -A
git commit -m "type(scope): description"
```

See `.github/instructions/python.instructions.md` for conventional commit format.

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

## If CI Fails

```bash
gh run view <run-id> --log-failed
```

Then use `cicd-debug` skill to diagnose.
