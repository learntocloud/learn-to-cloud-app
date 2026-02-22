# Research: Remaining Test Gaps

## Current State (post core + service test work)

**Overall**: 78% line coverage (3838 stmts, 830 missed). Target: `fail_under = 40` in `pyproject.toml`.

### Already Fully Tested (skip)

These modules are at 85%+ and have dedicated test files:

- All `core/` modules (auth, cache, config, csrf, database, github_client, llm_client, logger, metrics, middleware, observability, ratelimit, templates)
- `models.py` (100%), `schemas.py` (95%)
- All repositories except `submission_repository` (81%) and `user_repository` (82%)
- `services/`: content, ctf, dashboard, networking_lab, phase_requirements, progress, steps, verification_events, llm_verification_base, token_verification_base

---

## Files Below 85% — Grouped by Layer

### Tier 1: Rendering Layer (no test files exist)

| File | Stmts | Miss | Coverage | Test File |
|------|-------|------|----------|-----------|
| `rendering/context.py` | 55 | 26 | **53%** | **None** |
| `rendering/steps.py` | 47 | 15 | **68%** | **None** |

These contain **pure functions** with zero I/O — easiest to test, highest coverage-per-effort.

#### `rendering/context.py` — Uncovered Functions

| Function | Lines | What it does | Testability |
|----------|-------|-------------|-------------|
| `build_phase_topics()` | 173–203 | Merges phase topics with progress data → template-ready dicts | Pure function — takes `Phase` + `PhaseDetailProgress`, returns `(list, dict)` |
| `build_feedback_tasks()` | 206–234 | Parses JSON feedback string → `(tasks_list, passed_count)` | Pure function — takes `str | None`, returns tuple |
| `build_feedback_tasks_from_results()` | 237–260 | Same as above but from `TaskResult` objects | Pure function — takes `list[TaskResult] | None` |
| `build_topic_nav()` | 263–298 | Builds prev/next navigation for topic page | Pure function — takes `list[Topic]`, slug, phase_id, phase_name |
| `build_progress_dict()` | 161–170 | Returns `{completed, total, percentage}` dict | Already covered indirectly |

All are pure data transformations. No mocking needed.

#### `rendering/steps.py` — Uncovered Functions

| Function | Lines | What it does | Testability |
|----------|-------|-------------|-------------|
| `_p_to_callout()` | 39–49 | Regex match → callout HTML div | Pure function |
| `_process_admonitions()` | 52–75 | Converts `> [!TIP]` blockquotes to styled callouts | Pure function — string in, string out |
| `_provider_sort_key()` | 78–87 | Returns sort priority for cloud providers | Pure function |
| `render_md()` | 88–104 | Markdown → HTML with admonition support | Pure function |
| `build_step_data()` | 107–149 | `LearningStep` → template dict with rendered markdown | Pure function — already partially covered |

Entirely pure markdown/HTML transformations. No external dependencies.

---

### Tier 2: Services With Existing Tests But Low Coverage

| File | Coverage | Missing Lines | What's Uncovered |
|------|----------|------------|------------------|
| `services/users_service.py` | **53%** | 21, 36, 53-60, 68-69, 74-80, 100-125 | `normalize_github_username`, `parse_display_name`, `_to_user_response`, `get_user_by_id` (cache hit/miss), `ensure_user_exists`, `get_or_create_user`, `get_or_create_user_from_github` |
| `services/analytics_service.py` | **50%** | 140-207, 229-242, 259-264 | `_compute_analytics` (DB aggregation), `refresh_analytics` (snapshot persist), `analytics_refresh_loop` (background loop) |
| `services/hands_on_verification_service.py` | **77%** | 57-61, 81-90, 150-154, 164-168, 201, 231-233, 260-265 | `validate_ctf_token_submission` body, `validate_networking_token_submission` body (cloud_provider extraction), metrics recording in `validate_submission`, `GITHUB_PROFILE`/`SECURITY_SCANNING` dispatch branches |
| `services/submissions_service.py` | **76%** | 101-151, 249, 264-270, 279, 295, 298-306, 367, 500, 509 | `build_submission_context` (feedback parsing, cooldown calc), some edge paths in `submit_validation` |
| `services/github_hands_on_verification_service.py` | **61%** | 164-179, 194-215, 234-263, 286-309 | `_check_github_url_exists_with_retry` (HTTP internals), `check_github_url_exists` (error branches), `_check_repo_is_fork_of_with_retry`, `check_repo_is_fork_of` (error branches) |
| `services/pr_verification_service.py` | **76%** | 122-167, 212-216, 245-255, 287-313 | `_fetch_pr_files` internals, retriable/circuit-breaker catches, file-match result rendering |
| `services/code_verification_service.py` | **52%** | 299-342, 459-460, 538-543, 568-578, 592-684, 715-768 | `_fetch_repository_files` (GitHub API), `analyze_repository_code` end-to-end flow, prompt construction, LLM response handling |
| `services/devops_verification_service.py` | **52%** | 221-235, 274-304, 318-355, 442-500, 561, 568-572 | `_fetch_repo_tree` (GitHub API), `_fetch_file_contents` (GitHub API), `analyze_devops_repository` end-to-end flow |
| `services/security_verification_service.py` | **49%** | 69-97, 119-128, 136-149, 171-199, 247, 252-257, 315, 319-360 | `fetch_repo_tree` (GitHub API), `_build_scan_prompt`, `_run_security_scan` (LLM), `validate_security_scanning` end-to-end flow |
| `services/deployed_api_verification_service.py` | **80%** | 89-101, 107-109, 143, etc. | SSRF check internals, some HTTP error paths, circuit breaker branches |

---

### Tier 3: Routes & Infrastructure (lower ROI)

| File | Coverage | Notes |
|------|----------|-------|
| `routes/htmx_routes.py` | **70%** | LLM async path, SSE streaming, cooldown/concurrent error handlers, `_render_result_card`, background verification task |
| `main.py` | **57%** | App startup/lifespan — integration territory |
| `core/database.py` | **48%** | Infra wiring (`create_engine`, `warm_pool`, etc.) — logic parts already tested |
| `core/observability.py` | **73%** | OTel SDK wiring — fragile, zero business value |

---

## What's Worth Testing (Prioritized)

### Priority 1: Rendering Layer — New Test Files

**Create `api/tests/rendering/test_context.py` and `api/tests/rendering/test_steps.py`**

These are pure functions, zero dependencies, highest ROI. No mocking needed at all.

#### `test_context.py` (~15 tests)

```python
# build_feedback_tasks — pure JSON parsing
def test_valid_json():
    tasks, passed = build_feedback_tasks('[{"task_name":"A","passed":true,"feedback":"ok"}]')
    assert len(tasks) == 1
    assert passed == 1

def test_none_input():
    tasks, passed = build_feedback_tasks(None)
    assert tasks == []

def test_invalid_json():
    tasks, passed = build_feedback_tasks("not json")
    assert tasks == []

# build_feedback_tasks_from_results — pure object conversion
# build_phase_topics — Phase + PhaseDetailProgress → (topics_list, progress_dict)
# build_topic_nav — prev/next navigation
```

#### `test_steps.py` (~12 tests)

```python
# render_md — markdown → HTML
def test_basic_markdown():
    assert "<p>hello</p>" in render_md("hello")

def test_falsy_input():
    assert render_md("") == ""
    assert render_md(None) == ""

# _process_admonitions — blockquote callout conversion
def test_tip_admonition():
    html = '<blockquote><p>[!TIP] Use this.</p></blockquote>'
    result = _process_admonitions(html)
    assert 'callout-tip' in result

# _provider_sort_key — cloud provider ordering
def test_azure_first():
    assert _provider_sort_key("azure") < _provider_sort_key("aws")
    assert _provider_sort_key("aws") < _provider_sort_key("gcp")

# build_step_data — LearningStep → template dict
```

---

### Priority 2: `users_service.py` — Extend Existing Tests

**Extend `api/tests/services/test_users_service.py`** — currently only tests `delete_user_account`. Missing:

| Function | What to test |
|----------|-------------|
| `normalize_github_username()` | Lowercase, None, empty string |
| `parse_display_name()` | Single name, multi-part, empty, None |
| `get_user_by_id()` | Cache hit, cache miss (DB query + cache set), user not found |
| `ensure_user_exists()` | Calls `get_or_create` |
| `get_or_create_user()` | User exists, user doesn't exist (creates) |
| `get_or_create_user_from_github()` | New user, returning user, username conflict (clears old owner) |

All testable with mock `AsyncSession` + patched `UserRepository`. The pure functions (`normalize_github_username`, `parse_display_name`) need zero mocking.

---

### Priority 3: `hands_on_verification_service.py` — Extend Existing Tests

**Extend `api/tests/services/test_hands_on_verification_service.py`** — missing:

| Function | What to test |
|----------|-------------|
| `validate_ctf_token_submission()` | Delegates to `ctf_service`, maps result correctly |
| `validate_networking_token_submission()` | Delegates to `networking_lab_service`, extracts `cloud_provider` |
| `_dispatch_validation()` for `GITHUB_PROFILE` | Dispatches to `validate_github_profile` |
| `_dispatch_validation()` for `SECURITY_SCANNING` | Dispatches to `validate_security_scanning` |

These are routing tests — mock the underlying service and verify delegation.

---

### Priority 4: `submissions_service.py` — Extend Existing Tests

**Extend `api/tests/services/test_submissions_service.py`** — missing:

| Function | What to test |
|----------|-------------|
| `build_submission_context()` | Fetches submissions, parses feedback JSON, calculates cooldown |

This is the `PhaseSubmissionContext` builder used by phase page rendering.

---

### Priority 5: LLM Verification Services — Higher Effort

These three services (`code_verification`, `devops_verification`, `security_verification`) have **end-to-end flows** that:
1. Fetch repo file trees from GitHub API
2. Build LLM prompts
3. Call `get_llm_chat_client()` → structured output
4. Parse/sanitize responses

**Current tests** cover task definitions, prompt construction, response parsing, and file filtering — but NOT the end-to-end flow (`analyze_*` functions). Testing these requires mocking both GitHub API and LLM client.

Worth doing but higher cost per test.

---

### Priority 6: GitHub HTTP Internals (diminishing returns)

`_check_github_url_exists_with_retry`, `_check_repo_is_fork_of_with_retry`, `_fetch_pr_files` — these are HTTP calls wrapped in retry + circuit breaker. Testing them means:
- Mocking `httpx.AsyncClient` responses
- Resetting circuit breaker state between tests
- Potentially patching or disabling retry decorators

The existing tests mock *above* the circuit breaker (at `check_github_url_exists`), which is the pragmatic choice. Going deeper has diminishing returns.

---

### Not Worth Testing

| File | Why |
|------|-----|
| `main.py` (57%) | App startup lifespan — exercised by smoke/integration tests |
| `core/database.py` (48%) | Infra wiring. Logic parts (`get_db`, `check_db_connection`, pool checkout) already tested |
| `core/observability.py` (73%) | OTel SDK wiring — would be 100% mock assertions |
| `routes/htmx_routes.py` LLM/SSE paths | Complex integration (SSE, background tasks, template rendering). Route tests already cover sync paths. |

---

## Existing Test Conventions (recap)

All new tests must follow:
- Module docstring listing coverage scope
- `@pytest.mark.unit` on test classes
- `@pytest.mark.asyncio` on async test methods
- `autospec=True` on all `patch()` calls
- Test classes grouped by logical concern
- Private `_make_*()` helper factories
- `autouse` fixtures for state cleanup
- No database access in unit tests

For **rendering tests** specifically:
- No `__init__.py` exists in `api/tests/rendering/` — must create it
- Pure functions = no mocking, no fixtures, no async — simplest tests in the codebase
- Follow the pattern from `test_llm_verification_base.py` which also tests pure helpers

---

## Summary: Prioritized Action Items

| # | Action | Files | Est. Tests | ROI |
|---|--------|-------|-----------|-----|
| 1 | Create `tests/rendering/test_context.py` | New | ~15 | **Highest** — pure functions, zero mocking |
| 2 | Create `tests/rendering/test_steps.py` | New | ~12 | **Highest** — pure functions, zero mocking |
| 3 | Extend `tests/services/test_users_service.py` | Existing | ~12 | **High** — covers `normalize_github_username`, `parse_display_name`, `get_user_by_id` cache logic, `get_or_create_user_from_github` |
| 4 | Extend `tests/services/test_hands_on_verification_service.py` | Existing | ~6 | **Medium** — covers uncovered dispatch branches |
| 5 | Extend `tests/services/test_submissions_service.py` | Existing | ~5 | **Medium** — covers `build_submission_context` |
| 6 | Extend `tests/services/test_analytics_service.py` | Existing | ~4 | **Medium** — covers `_compute_analytics` with mocked repo |
| 7 | End-to-end tests for LLM verification services | Existing (3 files) | ~9 | **Lower** — high mocking cost (GitHub API + LLM client) |

**Total: ~63 new tests across 5 new/extended files (priorities 1-5), plus ~13 more for priorities 6-7.**

---

## Potential Gotchas

### 1. `rendering/` Tests Need `__init__.py`
No `tests/rendering/` directory exists. Must create `api/tests/rendering/__init__.py`.

### 2. `build_phase_topics` Requires Real Schema Objects
Takes `Phase` and `PhaseDetailProgress` — both are frozen Pydantic models. Must construct complete objects. Use the same `_make_topic()` / `_make_phase()` helpers from `test_progress_service.py`.

### 3. `build_topic_nav` Edge Cases
- Current slug not found in topics → returns `(None, None)`
- First topic → prev is phase link
- Last topic → next is phase link
- Single topic → both are phase link

### 4. `_process_admonitions` Is Regex-Heavy
Testing admonition processing requires precise HTML strings matching what `markdown.Markdown` produces (e.g., `<blockquote>\n<p>[!TIP] text</p>\n</blockquote>`).

### 5. `users_service` Cache Testing
`get_user_by_id` reads from `_user_cache` (TTLCache). Tests must clear the cache between tests using the same `autouse` pattern from `test_cache.py`.

### 6. `build_submission_context` Has Time-Dependent Logic
Cooldown calculation uses `datetime.now(UTC) - sub.updated_at`. Tests need to either freeze time (via `patch`) or use a recent enough timestamp.
