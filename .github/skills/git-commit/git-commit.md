---
name: git-commit
description: Run pre-commit hooks, generate a meaningful commit message from changed files, and push code. Use when committing and pushing changes, running pre-commit checks, or generating commit messages.
---

# Git Commit Workflow

## Overview

This skill automates the git commit workflow:
1. Run pre-commit hooks to lint/format code
2. Analyze changed files to generate a descriptive commit message
3. Commit and push to remote

## Step-by-Step Process

### Step 1: Run Pre-commit Hooks

Run pre-commit on all staged files:
```bash
pre-commit run --all-files
```

If pre-commit fails, fix the issues before proceeding. Common fixes are auto-applied (formatting, trailing whitespace).

If files were modified by pre-commit, stage them again:
```bash
git add -u
```

### Step 2: Analyze Changes with get_changed_files

Use the `get_changed_files` tool to inspect what has changed:
- Review staged changes to understand what's being committed
- Look at file paths and diff content
- Identify the type of change (feature, fix, refactor, docs, test, chore)

### Step 3: Write a Good Commit Message

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short description>

<optional body with more details>
```

**Types:**
| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change that neither fixes nor adds |
| `test` | Adding or updating tests |
| `chore` | Maintenance, deps, config |

**Scope examples:** `api`, `frontend`, `infra`, `content`, `skills`

**Good commit message examples:**
```
feat(api): add streak forgiveness for weekends

fix(frontend): resolve badge display issue on mobile

docs(skills): add git-commit workflow skill

chore(deps): update fastapi to 0.109.0
```

### Step 4: Commit and Push

Commit with the generated message:
```bash
git commit -m "<type>(<scope>): <description>"
```

Push to remote:
```bash
git push
```

Or push and set upstream for new branches:
```bash
git push -u origin <branch-name>
```

### Step 5: Watch CI Workflow

After pushing, the deploy workflow is automatically triggered. Get the latest run and monitor it:
```bash
gh run list --limit 1
gh run watch <run-id>
```

This will stream the workflow output in real-time. If the run fails, report the errors to the user.

**Alternative commands:**
```bash
# View a specific run details
gh run view <run-id>

# View failed run logs
gh run view <run-id> --log-failed
```

## Complete Workflow Example

```bash
# 1. Stage changes
git add -A

# 2. Run pre-commit
pre-commit run --all-files

# 3. Re-stage if pre-commit modified files
git add -u

# 4. Use get_changed_files tool to review changes and generate message

# 5. Commit
git commit -m "feat(api): add new badge verification endpoint"

# 6. Push
git push

# 7. Watch CI (get latest run ID first)
gh run list --limit 1
gh run watch <run-id>
```

## Troubleshooting

**Pre-commit not installed:**
```bash
pip install pre-commit
pre-commit install
```

**ty (type checker) not installed:**
```bash
pip install ty
```

**Pre-commit fails repeatedly:**
```bash
# Skip specific hooks temporarily
SKIP=ty pre-commit run --all-files

# Or run specific hook only
pre-commit run ruff --all-files
pre-commit run ty --all-files
```

**Nothing to commit after pre-commit:**
Pre-commit may have fixed all issues and there are no actual code changes. Review with `git status`.

## Tips for Good Commit Messages

1. **Be specific** - "fix bug" is bad, "fix null pointer in user auth" is good
2. **Use imperative mood** - "add feature" not "added feature"
3. **Keep subject line under 72 chars**
4. **Reference issues** - "fix(auth): handle expired tokens (#123)"
5. **Group related changes** - Don't mix unrelated changes in one commit
