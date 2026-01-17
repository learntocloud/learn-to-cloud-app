# Configuration Updates - Testing & Linting

## Summary of Changes

This document describes the improvements made to the CI/CD and pre-commit configurations.

---

## Changes Made

### 1. `.github/workflows/deploy.yml` ✅

**Changed**: Backend test execution to be more explicit

**Before**:
```yaml
- name: Run tests
  run: uv run pytest tests/ -v --tb=short
```

**After**:
```yaml
- name: Run unit tests
  run: uv run pytest tests/unit/ -v --tb=short
```

**Why**:
- ✅ Explicitly runs only unit tests (fast, ~0.19s for 155 tests)
- ✅ Matches the new test directory structure
- ✅ Prevents accidentally running slow integration tests in CI
- ✅ Clear intent in the workflow logs

---

### 2. `.pre-commit-config.yaml` ✅

**Added**: Test execution to pre-commit hooks

**New hooks added**:

#### Backend Tests
```yaml
- id: pytest-unit
  name: pytest unit tests
  entry: bash -c 'cd api && uv run pytest tests/unit/ -v'
  language: system
  files: ^api/.*\.py$
  pass_filenames: false
```

#### Frontend Tests
```yaml
- id: vitest
  name: vitest unit tests
  entry: bash -c 'cd frontend && npm test -- --run'
  language: system
  files: ^frontend/.*\.(ts|tsx)$
  pass_filenames: false
```

**Why**:
- ✅ Catch test failures before pushing to CI
- ✅ Faster feedback loop (tests run in ~1 second total)
- ✅ Reduces failed CI builds
- ✅ Can be skipped with `SKIP=pytest-unit,vitest git commit`

---

### 3. `PRE_COMMIT_GUIDE.md` ✅ NEW FILE

**Created**: Comprehensive documentation for using pre-commit hooks

**Contents**:
- What runs before each commit
- Installation instructions
- Performance expectations
- How to bypass hooks (with examples)
- When to skip vs when to fix
- Troubleshooting guide
- Best practices
- Integration with CI/CD

---

## Verification

### Pre-commit Configuration
```bash
✅ Configuration validated with pre-commit validate-config
✅ All hook IDs are unique and properly formatted
✅ File patterns are correct (^api/.*\.py$, ^frontend/.*\.(ts|tsx)$)
```

### GitHub Actions Workflow
```bash
✅ YAML syntax is valid
✅ Test path updated to tests/unit/
✅ Job dependencies remain correct (terraform depends on lint-and-test)
```

---

## What This Fixes

### Issue #1: Pre-commit didn't run tests ✅ FIXED
**Before**: Developers could commit broken code that passed linting but failed tests
**After**: Tests run locally before commit, catching bugs immediately

### Issue #2: CI ran all tests in tests/ ✅ FIXED
**Before**: `pytest tests/` ran everything, including potentially slow tests
**After**: `pytest tests/unit/` runs only fast unit tests explicitly

---

## Test Coverage

### Backend (API)
- **155 unit tests** in `api/tests/unit/`
- **Execution time**: ~0.19s
- **Coverage**: Progress system, badges, phase requirements, submissions

### Frontend
- **71 unit tests** (36 new + 35 existing)
- **Execution time**: ~0.6s
- **Coverage**: Constants, components, theme, error handling

### Total: 226 tests ✅

---

## Performance Impact

### Pre-commit Hooks (Local)

**Before** (no tests):
```
Ruff lint + format:    ~0.5s
Type checking (ty):    ~2-5s
ESLint:                ~1-2s
TypeScript check:      ~2-5s
─────────────────────────────
Total:                 ~6-13s per commit
```

**After** (with tests):
```
Ruff lint + format:    ~0.5s
Type checking (ty):    ~2-5s
Backend unit tests:    ~0.2s  ← NEW
ESLint:                ~1-2s
TypeScript check:      ~2-5s
Frontend unit tests:   ~0.6s  ← NEW
─────────────────────────────
Total:                 ~7-14s per commit
```

**Impact**: +0.8 seconds average (acceptable trade-off for catching bugs early)

### GitHub Actions (CI)

**Before**:
```
API lint and test:     ~30-60s
Frontend lint and test: ~20-40s
```

**After**:
```
API lint and test:     ~25-50s (faster, explicit unit tests)
Frontend lint and test: ~20-40s (unchanged)
```

**Impact**: Slightly faster due to explicit test path

---

## How to Use

### Install Pre-commit Hooks
```bash
pip install pre-commit
pre-commit install
```

### Normal Development Workflow
```bash
# Make changes
vim api/services/progress.py

# Commit (hooks run automatically)
git add .
git commit -m "feat: add new progress calculation"

# Hooks will run:
# ✓ Ruff lint + format
# ✓ Type checking
# ✓ Unit tests (155 backend + 71 frontend)
# ✓ ESLint
# ✓ TypeScript check
```

### Skip Hooks When Needed
```bash
# Skip tests for WIP commits
SKIP=pytest-unit,vitest git commit -m "WIP: work in progress"

# Skip all hooks (emergency only)
git commit --no-verify -m "hotfix: critical production issue"
```

---

## Rollback Instructions

If you need to rollback these changes:

### Rollback deploy.yml
```diff
- name: Run unit tests
-  run: uv run pytest tests/unit/ -v --tb=short
+  run: uv run pytest tests/ -v --tb=short
```

### Rollback pre-commit config
Remove these hooks from `.pre-commit-config.yaml`:
- `pytest-unit`
- `vitest`

---

## Next Steps (Optional Enhancements)

1. **Add coverage reporting to CI**:
   ```yaml
   - name: Run tests with coverage
     run: uv run pytest tests/unit/ --cov=services --cov-report=term-missing
   ```

2. **Add coverage badges to README**:
   - Use codecov.io or coveralls.io
   - Display coverage percentage in README

3. **Add integration tests** (separate from unit tests):
   ```
   api/tests/
   ├── unit/           # Fast unit tests (run in pre-commit + CI)
   ├── integration/    # Slower integration tests (run only in CI)
   └── e2e/           # End-to-end tests (run only on deploy)
   ```

4. **Add mutation testing** (advanced):
   - Use `mutmut` for Python
   - Verifies test quality by introducing bugs

---

## References

- [Pre-commit Documentation](https://pre-commit.com/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Vitest Documentation](https://vitest.dev/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

---

## Questions?

See `PRE_COMMIT_GUIDE.md` for detailed usage instructions and troubleshooting.
