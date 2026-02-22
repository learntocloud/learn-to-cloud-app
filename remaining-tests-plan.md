# Plan: Remaining Tests

## Approach

Cover the highest-ROI gaps identified in the research: the **rendering layer** (2 brand-new test files for pure functions), then **extend existing test files** for `users_service`, `hands_on_verification_service`, and `submissions_service`.

**Why these 5 targets**: Rendering functions are pure data transformations (zero mocking, highest coverage-per-effort). The three service files have existing test files with clear gaps in already-testable functions. Together these ~55 tests close the biggest holes without touching fragile infrastructure or LLM integration paths.

**Not in scope**: LLM verification end-to-end flows (`code_verification`, `devops_verification`, `security_verification`), GitHub HTTP/circuit-breaker internals, `routes/htmx_routes.py` SSE/async paths, `main.py`, `core/database.py` infra wiring. These have diminishing returns or require heavy mock scaffolding.

---

## Files

| Action | File | Target |
|--------|------|--------|
| Create | `api/tests/rendering/__init__.py` | Package init |
| Create | `api/tests/rendering/test_context.py` | `rendering/context.py` (53% → ~95%) |
| Create | `api/tests/rendering/test_steps.py` | `rendering/steps.py` (68% → ~95%) |
| Extend | `api/tests/services/test_users_service.py` | `services/users_service.py` (53% → ~90%) |
| Extend | `api/tests/services/test_hands_on_verification_service.py` | `services/hands_on_verification_service.py` (77% → ~90%) |
| Extend | `api/tests/services/test_submissions_service.py` | `services/submissions_service.py` (76% → ~85%) |

---

## File 1: `api/tests/rendering/__init__.py`

```python
"""Rendering tests package."""
```

---

## File 2: `api/tests/rendering/test_context.py`

All pure functions — no mocking, no async, no fixtures needed.

```python
"""Unit tests for rendering.context module.

Tests cover:
- build_progress_dict percentage calculation
- build_feedback_tasks JSON parsing and counting
- build_feedback_tasks_from_results object conversion
- build_phase_topics merges topics with progress
- build_topic_nav prev/next navigation
"""

import pytest

from rendering.context import (
    build_feedback_tasks,
    build_feedback_tasks_from_results,
    build_phase_topics,
    build_progress_dict,
    build_topic_nav,
)
from schemas import (
    LearningStep,
    Phase,
    PhaseDetailProgress,
    TaskResult,
    Topic,
    TopicProgressData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_topic(topic_id: str, slug: str, name: str = "") -> Topic:
    return Topic(
        id=topic_id,
        slug=slug,
        name=name or slug,
        description="",
        order=0,
        learning_steps=[LearningStep(id="s1", order=0)],
    )


# ---------------------------------------------------------------------------
# build_progress_dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildProgressDict:
    def test_basic(self):
        result = build_progress_dict(3, 10)
        assert result == {"completed": 3, "total": 10, "percentage": 30}

    def test_zero_total(self):
        result = build_progress_dict(0, 0)
        assert result["percentage"] == 0

    def test_full(self):
        result = build_progress_dict(5, 5)
        assert result["percentage"] == 100


# ---------------------------------------------------------------------------
# build_feedback_tasks
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildFeedbackTasks:
    def test_valid_json(self):
        json_str = '[{"task_name":"A","passed":true,"feedback":"ok"},{"task_name":"B","passed":false,"feedback":"nope"}]'
        tasks, passed = build_feedback_tasks(json_str)
        assert len(tasks) == 2
        assert passed == 1
        assert tasks[0]["name"] == "A"
        assert tasks[0]["passed"] is True
        assert tasks[1]["message"] == "nope"

    def test_none_input(self):
        tasks, passed = build_feedback_tasks(None)
        assert tasks == []
        assert passed == 0

    def test_empty_string(self):
        tasks, passed = build_feedback_tasks("")
        assert tasks == []
        assert passed == 0

    def test_invalid_json(self):
        tasks, passed = build_feedback_tasks("not json")
        assert tasks == []
        assert passed == 0

    def test_all_passed(self):
        json_str = '[{"task_name":"A","passed":true,"feedback":""},{"task_name":"B","passed":true,"feedback":""}]'
        _, passed = build_feedback_tasks(json_str)
        assert passed == 2

    def test_missing_fields_use_defaults(self):
        json_str = '[{}]'
        tasks, passed = build_feedback_tasks(json_str)
        assert tasks[0]["name"] == ""
        assert tasks[0]["passed"] is False
        assert tasks[0]["message"] == ""
        assert passed == 0


# ---------------------------------------------------------------------------
# build_feedback_tasks_from_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildFeedbackTasksFromResults:
    def test_with_results(self):
        results = [
            TaskResult(task_name="Task A", passed=True, feedback="Good"),
            TaskResult(task_name="Task B", passed=False, feedback="Fix this"),
        ]
        tasks, passed = build_feedback_tasks_from_results(results)
        assert len(tasks) == 2
        assert passed == 1
        assert tasks[0]["name"] == "Task A"
        assert tasks[1]["message"] == "Fix this"

    def test_none_input(self):
        tasks, passed = build_feedback_tasks_from_results(None)
        assert tasks == []
        assert passed == 0

    def test_empty_list(self):
        tasks, passed = build_feedback_tasks_from_results([])
        assert tasks == []
        assert passed == 0


# ---------------------------------------------------------------------------
# build_phase_topics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildPhaseTopics:
    def test_merges_topics_with_progress(self):
        topic = _make_topic("phase0-t1", "basics", "Basics")
        phase = Phase(
            id=0, name="P0", slug="phase0", order=0, topics=[topic],
        )
        detail = PhaseDetailProgress(
            topic_progress={
                "phase0-t1": TopicProgressData(
                    steps_completed=1, steps_total=3, percentage=33.3, status="in_progress",
                ),
            },
            steps_completed=1,
            steps_total=3,
            percentage=33,
        )
        topics, progress = build_phase_topics(phase, detail)
        assert len(topics) == 1
        assert topics[0]["name"] == "Basics"
        assert topics[0]["slug"] == "basics"
        assert topics[0]["progress"]["completed"] == 1
        assert progress["percentage"] == 33

    def test_topic_without_progress(self):
        topic = _make_topic("phase0-t1", "basics")
        phase = Phase(id=0, name="P0", slug="phase0", order=0, topics=[topic])
        detail = PhaseDetailProgress(
            topic_progress={}, steps_completed=0, steps_total=3, percentage=0,
        )
        topics, _ = build_phase_topics(phase, detail)
        assert topics[0]["progress"] is None


# ---------------------------------------------------------------------------
# build_topic_nav
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildTopicNav:
    def _topics(self) -> list[Topic]:
        return [
            _make_topic("t1", "first", "First"),
            _make_topic("t2", "second", "Second"),
            _make_topic("t3", "third", "Third"),
        ]

    def test_middle_topic(self):
        prev_t, next_t = build_topic_nav(self._topics(), "second", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["slug"] == "first"
        assert next_t is not None
        assert next_t["slug"] == "third"

    def test_first_topic_prev_is_phase_link(self):
        prev_t, next_t = build_topic_nav(self._topics(), "first", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["slug"] is None
        assert prev_t["url"] == "/phase/0"
        assert next_t is not None
        assert next_t["slug"] == "second"

    def test_last_topic_next_is_phase_link(self):
        prev_t, next_t = build_topic_nav(self._topics(), "third", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["slug"] == "second"
        assert next_t is not None
        assert next_t["slug"] is None
        assert next_t["url"] == "/phase/0"

    def test_unknown_slug_returns_none(self):
        prev_t, next_t = build_topic_nav(self._topics(), "nonexistent", 0, "Phase 0")
        assert prev_t is None
        assert next_t is None

    def test_single_topic(self):
        topics = [_make_topic("t1", "only", "Only")]
        prev_t, next_t = build_topic_nav(topics, "only", 0, "Phase 0")
        assert prev_t is not None
        assert prev_t["url"] == "/phase/0"
        assert next_t is not None
        assert next_t["url"] == "/phase/0"
```

---

## File 3: `api/tests/rendering/test_steps.py`

All pure functions — no mocking.

```python
"""Unit tests for rendering.steps module.

Tests cover:
- render_md markdown to HTML conversion
- _process_admonitions blockquote callout conversion
- _provider_sort_key cloud provider ordering
- build_step_data LearningStep to template dict
"""

import pytest

from rendering.steps import (
    _process_admonitions,
    _provider_sort_key,
    build_step_data,
    render_md,
)
from schemas import LearningStep, ProviderOption


# ---------------------------------------------------------------------------
# render_md
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderMd:
    def test_basic_paragraph(self):
        result = render_md("hello world")
        assert "<p>" in result
        assert "hello world" in result

    def test_empty_string(self):
        assert render_md("") == ""

    def test_none(self):
        assert render_md(None) == ""

    def test_fenced_code(self):
        result = render_md("```python\nprint('hi')\n```")
        assert "<code" in result

    def test_admonition_tip(self):
        result = render_md("> [!TIP] Use this.")
        assert "callout-tip" in result
        assert "Use this." in result

    def test_admonition_warning(self):
        result = render_md("> [!WARNING] Be careful.")
        assert "callout-warning" in result

    def test_admonition_note(self):
        result = render_md("> [!NOTE] Take note.")
        assert "callout-note" in result

    def test_admonition_important(self):
        result = render_md("> [!IMPORTANT] Do this.")
        assert "callout-important" in result

    def test_regular_blockquote_unchanged(self):
        result = render_md("> Just a normal quote.")
        assert "<blockquote>" in result


# ---------------------------------------------------------------------------
# _process_admonitions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessAdmonitions:
    def test_no_blockquote_unchanged(self):
        html = "<p>hello</p>"
        assert _process_admonitions(html) == html

    def test_blockquote_without_admonition_unchanged(self):
        html = "<blockquote><p>normal quote</p></blockquote>"
        assert _process_admonitions(html) == html

    def test_single_admonition_unwraps_blockquote(self):
        html = "<blockquote>\n<p>[!TIP]\nUse this.</p>\n</blockquote>"
        result = _process_admonitions(html)
        assert "<blockquote>" not in result
        assert "callout-tip" in result
        assert "Use this." in result

    def test_mixed_content_keeps_blockquote(self):
        html = '<blockquote><p>[!TIP]\nUse this.</p><p>Normal text.</p></blockquote>'
        result = _process_admonitions(html)
        assert "<blockquote>" in result
        assert "callout-tip" in result


# ---------------------------------------------------------------------------
# _provider_sort_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProviderSortKey:
    def test_azure_first(self):
        assert _provider_sort_key("azure") == (0, "azure")

    def test_aws_second(self):
        assert _provider_sort_key("aws") == (1, "aws")

    def test_gcp_third(self):
        assert _provider_sort_key("gcp") == (2, "gcp")

    def test_unknown_last(self):
        assert _provider_sort_key("other") == (3, "other")

    def test_case_insensitive(self):
        assert _provider_sort_key("Azure") == (0, "azure")

    def test_empty_string(self):
        assert _provider_sort_key("") == (3, "")

    def test_ordering(self):
        assert _provider_sort_key("azure") < _provider_sort_key("aws")
        assert _provider_sort_key("aws") < _provider_sort_key("gcp")
        assert _provider_sort_key("gcp") < _provider_sort_key("other")


# ---------------------------------------------------------------------------
# build_step_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildStepData:
    def test_basic_step(self):
        step = LearningStep(
            id="step-1", order=0, title="Install", description="Do stuff",
        )
        data = build_step_data(step)
        assert data["id"] == "step-1"
        assert data["title"] == "Install"
        assert "<p>" in data["description_html"]

    def test_empty_optional_fields(self):
        step = LearningStep(id="step-1", order=0)
        data = build_step_data(step)
        assert data["action"] == ""
        assert data["title"] == ""
        assert data["url"] == ""
        assert data["code"] == ""

    def test_options_sorted_by_provider(self):
        step = LearningStep(
            id="step-1",
            order=0,
            options=[
                ProviderOption(provider="gcp", title="GCP Guide", url="https://gcp.dev", description=""),
                ProviderOption(provider="azure", title="Azure Guide", url="https://azure.dev", description=""),
                ProviderOption(provider="aws", title="AWS Guide", url="https://aws.dev", description=""),
            ],
        )
        data = build_step_data(step)
        providers = [o["provider"] for o in data["options"]]
        assert providers == ["azure", "aws", "gcp"]

    def test_custom_md_renderer(self):
        step = LearningStep(id="step-1", order=0, description="hello")
        data = build_step_data(step, md_renderer=lambda s: f"CUSTOM:{s}")
        assert data["description_html"] == "CUSTOM:hello"
```

---

## File 4: Extend `api/tests/services/test_users_service.py`

Add tests for all untested functions. Keep existing `TestDeleteUserAccount` intact.

**Add to imports:**
```python
from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    ensure_user_exists,
    get_or_create_user,
    get_or_create_user_from_github,
    get_user_by_id,
    normalize_github_username,
    parse_display_name,
)
```

**Add autouse fixture for cache cleanup:**
```python
@pytest.fixture(autouse=True)
def _clear_user_cache():
    from core.cache import _user_cache
    _user_cache.clear()
    yield
    _user_cache.clear()
```

**New test classes:**
```python
@pytest.mark.unit
class TestNormalizeGithubUsername:
    def test_lowercases(self):
        assert normalize_github_username("TestUser") == "testuser"

    def test_none_returns_none(self):
        assert normalize_github_username(None) is None

    def test_empty_returns_none(self):
        assert normalize_github_username("") is None

    def test_already_lowercase(self):
        assert normalize_github_username("testuser") == "testuser"


@pytest.mark.unit
class TestParseDisplayName:
    def test_full_name(self):
        assert parse_display_name("John Doe") == ("John", "Doe")

    def test_single_name(self):
        assert parse_display_name("John") == ("John", "")

    def test_multi_part_last_name(self):
        assert parse_display_name("John Van Doe") == ("John", "Van Doe")

    def test_none(self):
        assert parse_display_name(None) == ("", "")

    def test_empty_string(self):
        assert parse_display_name("") == ("", "")


@pytest.mark.unit
class TestGetUserById:
    @pytest.mark.asyncio
    async def test_returns_cached_user(self):
        from core.cache import set_cached_user
        mock_user = MagicMock()
        set_cached_user(1, mock_user)
        result = await get_user_by_id(AsyncMock(), user_id=1)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        mock_user = MagicMock()
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_user)
            result = await get_user_by_id(AsyncMock(), user_id=1)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)
            result = await get_user_by_id(AsyncMock(), user_id=999)
        assert result is None


@pytest.mark.unit
class TestGetOrCreateUserFromGithub:
    @pytest.mark.asyncio
    async def test_new_user(self):
        mock_user = MagicMock()
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_github_username = AsyncMock(return_value=None)
            repo.upsert = AsyncMock(return_value=mock_user)
            result = await get_or_create_user_from_github(
                AsyncMock(),
                github_id=123,
                first_name="Test",
                last_name="User",
                avatar_url="https://example.com/avatar.png",
                github_username="TestUser",
            )
        assert result is mock_user
        repo.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_username_conflict_clears_old_owner(self):
        old_owner = MagicMock()
        old_owner.id = 456
        new_user = MagicMock()
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_github_username = AsyncMock(return_value=old_owner)
            repo.clear_github_username = AsyncMock()
            repo.upsert = AsyncMock(return_value=new_user)
            await get_or_create_user_from_github(
                AsyncMock(),
                github_id=123,
                first_name="New",
                last_name="User",
                avatar_url=None,
                github_username="sharedname",
            )
        repo.clear_github_username.assert_awaited_once_with(456)
```

---

## File 5: Extend `api/tests/services/test_hands_on_verification_service.py`

Add tests for uncovered dispatch branches and token submission wrappers.

**New test classes** (append to existing file):

```python
@pytest.mark.unit
class TestValidateCtfTokenSubmission:
    def test_delegates_to_ctf_service(self):
        from services.hands_on_verification_service import validate_ctf_token_submission
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.message = "OK"
        mock_result.server_error = False
        with patch("services.hands_on_verification_service.verify_ctf_token", autospec=True, return_value=mock_result) as mock:
            result = validate_ctf_token_submission("token", "testuser")
        mock.assert_called_once_with("token", "testuser")
        assert result.is_valid is True


@pytest.mark.unit
class TestValidateNetworkingTokenSubmission:
    def test_extracts_cloud_provider(self):
        from services.hands_on_verification_service import validate_networking_token_submission
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.message = "OK"
        mock_result.server_error = False
        mock_result.challenge_type = "networking-lab-azure"
        with patch("services.hands_on_verification_service.verify_networking_token", autospec=True, return_value=mock_result):
            result = validate_networking_token_submission("token", "testuser")
        assert result.cloud_provider == "azure"

    def test_no_cloud_provider_when_invalid(self):
        from services.hands_on_verification_service import validate_networking_token_submission
        mock_result = MagicMock()
        mock_result.is_valid = False
        mock_result.message = "bad"
        mock_result.server_error = False
        mock_result.challenge_type = None
        with patch("services.hands_on_verification_service.verify_networking_token", autospec=True, return_value=mock_result):
            result = validate_networking_token_submission("token", "testuser")
        assert result.cloud_provider is None


@pytest.mark.unit
class TestDispatchGitHubProfile:
    @pytest.mark.asyncio
    async def test_github_profile_routes_correctly(self):
        requirement = _make_requirement(SubmissionType.GITHUB_PROFILE)
        with patch("services.github_hands_on_verification_service.validate_github_profile", autospec=True) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Verified!")
            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser",
                expected_username="testuser",
            )
        mock.assert_called_once_with("https://github.com/testuser", "testuser")
        assert result.is_valid is True


@pytest.mark.unit
class TestDispatchSecurityScanning:
    @pytest.mark.asyncio
    async def test_security_scanning_routes_correctly(self):
        requirement = _make_requirement(SubmissionType.SECURITY_SCANNING)
        with patch("services.security_verification_service.validate_security_scanning", autospec=True) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="Scanned!")
            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://github.com/testuser/repo",
                expected_username="testuser",
            )
        mock.assert_called_once_with("https://github.com/testuser/repo", "testuser")
        assert result.is_valid is True
```

---

## File 6: Extend `api/tests/services/test_submissions_service.py`

Add tests for `get_phase_submission_context`.

**Add import:**
```python
from services.submissions_service import get_phase_submission_context
```

**New test class** (append):

```python
@pytest.mark.unit
class TestGetPhaseSubmissionContext:
    @pytest.mark.asyncio
    async def test_empty_submissions(self):
        with patch("services.submissions_service.SubmissionRepository", autospec=True) as MockRepo:
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(return_value=[])
            result = await get_phase_submission_context(AsyncMock(), user_id=1, phase_id=3)
        assert result.submissions_by_req == {}
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_submission_without_feedback(self):
        mock_sub = _make_mock_submission(is_validated=True)
        mock_sub.feedback_json = None
        with patch("services.submissions_service.SubmissionRepository", autospec=True) as MockRepo:
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(return_value=[mock_sub])
            result = await get_phase_submission_context(AsyncMock(), user_id=1, phase_id=3)
        assert "test-requirement" in result.submissions_by_req
        assert result.feedback_by_req == {}

    @pytest.mark.asyncio
    async def test_submission_with_feedback_json(self):
        mock_sub = _make_mock_submission(is_validated=False, verification_completed=True)
        mock_sub.feedback_json = '[{"task_name":"A","passed":true,"feedback":"ok"}]'
        mock_sub.updated_at = datetime.now(UTC) - timedelta(hours=2)
        with (
            patch("services.submissions_service.SubmissionRepository", autospec=True) as MockRepo,
            patch("services.submissions_service.get_settings", autospec=True) as mock_settings,
        ):
            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(return_value=[mock_sub])
            result = await get_phase_submission_context(AsyncMock(), user_id=1, phase_id=3)
        assert "test-requirement" in result.feedback_by_req
        feedback = result.feedback_by_req["test-requirement"]
        assert feedback["passed"] == 1
        assert feedback["cooldown_seconds"] is None  # 2 hours > 1 hour cooldown

    @pytest.mark.asyncio
    async def test_cooldown_remaining_when_within_window(self):
        mock_sub = _make_mock_submission(is_validated=False, verification_completed=True)
        mock_sub.feedback_json = '[{"task_name":"A","passed":false,"feedback":"nope"}]'
        mock_sub.updated_at = datetime.now(UTC) - timedelta(minutes=5)
        with (
            patch("services.submissions_service.SubmissionRepository", autospec=True) as MockRepo,
            patch("services.submissions_service.get_settings", autospec=True) as mock_settings,
        ):
            mock_settings.return_value.code_analysis_cooldown_seconds = 3600
            MockRepo.return_value.get_by_user_and_phase = AsyncMock(return_value=[mock_sub])
            result = await get_phase_submission_context(AsyncMock(), user_id=1, phase_id=3)
        feedback = result.feedback_by_req["test-requirement"]
        assert feedback["cooldown_seconds"] is not None
        assert feedback["cooldown_seconds"] > 3000  # ~55 min remaining
```

---

## Trade-offs

### 1. Testing rendering via unit tests vs route integration tests
- **Chosen**: Direct unit tests. These are pure functions — calling them directly is faster, more precise, and doesn't require setting up a FastAPI test client with templates.
- **Rejected**: Testing only through route tests — too slow, too indirect, and the route tests already exist for HTTP-level behavior.

### 2. `users_service` depth — testing `_to_user_response` separately vs via `get_or_create_user`
- **Chosen**: Test `_to_user_response` implicitly through `get_or_create_user` which calls it. No separate test for a trivial field mapper.
- **Rejected**: Dedicated `TestToUserResponse` class — it's a 7-line field-by-field copy with no logic.

### 3. `submissions_service` — testing `build_submission_context` vs `submit_validation` gaps
- **Chosen**: Focus on `get_phase_submission_context` — it has the most uncovered logic (feedback parsing, cooldown calculation). The `submit_validation` gaps are edge paths in exception handling already partially covered.

### 4. LLM end-to-end tests deferred
- **Chosen**: Skip for this round. `analyze_repository_code`, `analyze_devops_repository`, `validate_security_scanning` end-to-end flows require mocking both GitHub API (file tree fetch) and LLM client (structured output). High effort, diminishing returns.

---

## Risks & Edge Cases

| Risk | Mitigation |
|------|-----------|
| `render_md` uses module-level `_md = markdown.Markdown(...)` singleton | `_md.reset()` is called inside `render_md()` — safe for sequential tests |
| `_process_admonitions` regex depends on exact HTML output from `markdown` lib | Test via `render_md()` (end-to-end) rather than crafting HTML manually for most cases; one test hits `_process_admonitions` directly for the mixed-content branch |
| `build_phase_topics` requires frozen Pydantic models | Construct `Phase`, `Topic`, `PhaseDetailProgress`, `TopicProgressData` directly — they're frozen but constructable |
| `get_user_by_id` uses `_user_cache` (global TTLCache) | `autouse` fixture clears cache before/after each test |
| `get_phase_submission_context` cooldown is time-dependent | Tests use `datetime.now(UTC) - timedelta(...)` for predictable elapsed times |
| `hands_on` dispatch tests use lazy imports (`from services.ctf_service import ...`) | Patch at the module where the function is defined (e.g., `services.hands_on_verification_service.verify_ctf_token`) since the import happens inside the function |
| Existing helpers in `test_submissions_service.py` (`_make_mock_submission`) may need `feedback_json` field | Already has the field — `_make_mock_submission` creates `MagicMock` with all submission attributes |

---

## Todo List

- [x] **Phase 1: Rendering tests** — Create test infrastructure + 2 test files ✅
  - [x] Create `api/tests/rendering/__init__.py`
  - [x] Create `api/tests/rendering/test_context.py` (16 tests)
  - [x] Create `api/tests/rendering/test_steps.py` (18 tests)
- [x] **Phase 2: users_service** — Extend `api/tests/services/test_users_service.py` (14 new tests) ✅
  - [x] Add imports and cache cleanup fixture
  - [x] `TestNormalizeGithubUsername` — lowercase, None, empty, already-lower
  - [x] `TestParseDisplayName` — full, single, multi-part, None, empty
  - [x] `TestGetUserById` — cache hit, cache miss, not found
  - [x] `TestGetOrCreateUserFromGithub` — new user, username conflict
- [x] **Phase 3: hands_on_verification** — Extend `api/tests/services/test_hands_on_verification_service.py` (5 new tests) ✅
  - [x] `TestValidateCtfTokenSubmission` — delegation
  - [x] `TestValidateNetworkingTokenSubmission` — cloud_provider extraction
  - [x] `TestDispatchGitHubProfile` — routing
  - [x] `TestDispatchSecurityScanning` — routing
- [x] **Phase 4: submissions_service** — Extend `api/tests/services/test_submissions_service.py` (4 new tests) ✅
  - [x] `TestGetPhaseSubmissionContext` — empty, no feedback, with feedback, cooldown
- [x] **Final: Run full test suite + lint** — 105 passed in 0.27s ✅
