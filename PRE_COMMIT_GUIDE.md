# Pre-commit Hooks Guide

This document explains how to use the pre-commit hooks in the Learn to Cloud App.

## What Runs Before Each Commit

The pre-commit hooks automatically run the following checks before allowing a commit:

### Backend (Python/API)
1. **Ruff linting** - Code style and quality checks with auto-fix
2. **Ruff formatting** - Code formatting
3. **Type checking (ty)** - Static type analysis
4. **Unit tests (pytest)** - All 155 unit tests in `api/tests/unit/`

### Frontend (TypeScript/React)
1. **ESLint** - JavaScript/TypeScript linting
2. **TypeScript checking** - Type validation
3. **Unit tests (vitest)** - All 71 unit tests

### General
- Trailing whitespace removal
- End-of-file fixing
- YAML/JSON validation
- Large file checks
- Merge conflict detection

## Installation

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# (Optional) Run on all files to verify setup
pre-commit run --all-files
```

## Performance

Expected commit time: **7-14 seconds**
- Ruff lint + format: ~0.5s
- Type checking (ty): ~2-5s
- ESLint: ~1-2s
- TypeScript check: ~2-5s
- Backend unit tests: ~0.2s
- Frontend unit tests: ~0.6s

## Bypassing Hooks

### Skip ALL pre-commit hooks
```bash
git commit --no-verify -m "Your commit message"
# or
git commit -n -m "Your commit message"
```

### Skip SPECIFIC hooks
```bash
# Skip only tests (useful for WIP commits)
SKIP=pytest-unit,vitest git commit -m "WIP: work in progress"

# Skip type checking
SKIP=ty,typescript git commit -m "Fix typo in comments"

# Skip multiple hooks
SKIP=pytest-unit,vitest,ty git commit -m "Quick fix"
```

### Available hook IDs to skip
- `trailing-whitespace`
- `end-of-file-fixer`
- `check-yaml`
- `check-json`
- `check-added-large-files`
- `check-merge-conflict`
- `ruff` (linting)
- `ruff-format` (formatting)
- `ty` (Python type checking)
- `pytest-unit` (Python unit tests)
- `eslint` (JavaScript/TypeScript linting)
- `typescript` (TypeScript type checking)
- `vitest` (Frontend unit tests)

## When to Skip Hooks

### ✅ Good reasons to skip
- **WIP commits**: `SKIP=pytest-unit,vitest git commit -m "WIP: halfway through feature"`
- **Documentation only**: `git commit --no-verify -m "docs: update README"`
- **Quick fixes in CI**: When you know CI will catch issues
- **Emergency hotfixes**: Time-critical production fixes

### ❌ Bad reasons to skip
- Tests are failing (fix the tests instead)
- Too lazy to wait (the hooks catch bugs early)
- Don't want to deal with type errors (these prevent runtime bugs)

## Troubleshooting

### Hook is too slow
```bash
# Profile which hook is slow
time pre-commit run --all-files

# Skip slow hooks temporarily
SKIP=ty,typescript git commit -m "Your message"
```

### Hook fails with "command not found"
```bash
# Make sure dependencies are installed
cd api && uv sync --extra dev
cd frontend && npm install

# Reinstall hooks
pre-commit clean
pre-commit install
```

### Want to update hook versions
```bash
# Update to latest versions
pre-commit autoupdate

# Run updated hooks on all files
pre-commit run --all-files
```

## CI/CD Integration

Pre-commit hooks run **locally before commit**. GitHub Actions runs the same checks **in CI**:

| Check | Pre-commit | GitHub Actions |
|-------|-----------|----------------|
| Ruff lint | ✅ Yes | ✅ Yes |
| Ruff format | ✅ Yes | ✅ Yes |
| Type check (ty) | ✅ Yes | ✅ Yes |
| Backend tests | ✅ Yes | ✅ Yes |
| ESLint | ✅ Yes | ✅ Yes |
| TypeScript | ✅ Yes | ✅ Yes |
| Frontend tests | ✅ Yes | ✅ Yes |
| Build check | ❌ No | ✅ Yes |

**Why this duplication?**
- **Pre-commit**: Fast feedback before pushing (catches 90% of issues)
- **CI**: Final verification and build checks (catches remaining 10%)

## Best Practices

1. **Let hooks run most of the time** - They catch bugs early
2. **Use `SKIP=` for WIP commits** - Better than `--no-verify`
3. **Fix issues, don't bypass** - Hooks exist for a reason
4. **Run `pre-commit run --all-files`** after updating dependencies
5. **Commit message discipline** - Use conventional commits (feat:, fix:, docs:, etc.)

## Examples

```bash
# Normal commit (all hooks run)
git commit -m "feat: add user authentication"

# WIP commit (skip tests)
SKIP=pytest-unit,vitest git commit -m "WIP: authentication in progress"

# Documentation commit (skip everything)
git commit --no-verify -m "docs: update API documentation"

# Fix linting issues first, then commit
pre-commit run --all-files
git add .
git commit -m "fix: resolve linting issues"

# Update pre-commit hooks
pre-commit autoupdate
pre-commit run --all-files
```

## Getting Help

If pre-commit hooks are causing issues:

1. Check this guide first
2. Run `pre-commit run --all-files --verbose` for detailed output
3. Check `.pre-commit-config.yaml` for configuration
4. Ask in team chat or create an issue

## Further Reading

- [pre-commit documentation](https://pre-commit.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [Vitest documentation](https://vitest.dev/)
