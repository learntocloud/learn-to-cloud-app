# API Test Review & Improvement Plan

## Executive Summary

**Current Grade: D+** (would be F without the good badge/progress tests)

The API tests are **inadequate for a production application**. While some tests (badges, progress) show good practices, the majority are shallow, repetitive, and fail to test critical scenarios.

### Key Problems

❌ **Shallow coverage** - Most tests only verify happy paths and basic status codes
❌ **Missing edge cases** - No testing of race conditions, concurrent operations, or complex scenarios
❌ **Weak validation** - Tests check that fields exist, not that values are correct
❌ **No service tests** - 18 service files, minimal direct testing
❌ **Poor error testing** - Error paths barely tested
❌ **No integration tests** - No end-to-end user flows
❌ **No performance tests** - No load testing or query optimization validation

---

## Current Test Analysis

### ✅ Good Tests (Keep These Patterns)

#### `test_badges.py` - **Grade: A**
- Comprehensive scenario testing
- Clear test names matching business rules
- Tests both success and failure cases
- References source of truth documentation
- Good use of parameterization

**Example of good testing:**
```python
def test_no_badge_with_partial_steps(self):
    """skill file: All steps must be completed."""
    phase_counts = {
        0: (10, 12, True),  # Only 10/15 steps
    }
    badges = compute_phase_badges(phase_counts)
    assert badges == []
```

#### `test_progress.py` - **Grade: A**
- Tests match documented requirements
- Comprehensive coverage of edge cases
- Clear business rule validation
- Good structure and organization

---

### ❌ Weak Tests (Need Major Improvement)

#### `test_routes.py` - **Grade: D**

**Problems:**

1. **Shallow Assertions** - Only checks field existence, not values
   ```python
   # Current (BAD):
   def test_get_dashboard(self, client: TestClient):
       response = client.get("/api/user/dashboard")
       assert response.status_code == 200
       data = response.json()
       assert "phases" in data  # Just checks key exists!

   # Should be (GOOD):
   def test_get_dashboard_returns_correct_structure(self, client: TestClient):
       response = client.get("/api/user/dashboard")
       assert response.status_code == 200
       data = response.json()

       # Validate structure
       assert isinstance(data["phases"], list)
       assert len(data["phases"]) == 7  # Expected number

       # Validate each phase has required fields
       for phase in data["phases"]:
           assert "id" in phase
           assert "name" in phase
           assert "progress" in phase
           assert 0 <= phase["progress"] <= 100
   ```

2. **Missing Edge Cases** - No boundary testing
   ```python
   # Missing tests:
   - What happens with very long answers (>10000 chars)?
   - What happens with malformed JSON?
   - What happens with SQL injection attempts?
   - What happens with concurrent step completions?
   - What happens with invalid UTF-8?
   ```

3. **No Error Detail Validation** - Errors not properly tested
   ```python
   # Current (BAD):
   def test_complete_step_sequential_required(self, client: TestClient):
       response = client.post(
           "/api/steps/complete",
           json={"topic_id": "phase0-topic1", "step_order": 3}
       )
       assert response.status_code == 400
       detail = response.json()["detail"].lower()
       assert "previous" in detail or "must complete" in detail  # Too vague!

   # Should be (GOOD):
   def test_complete_step_requires_previous_steps(self, client: TestClient):
       response = client.post(
           "/api/steps/complete",
           json={"topic_id": "phase0-topic1", "step_order": 3}
       )
       assert response.status_code == 400
       data = response.json()
       assert data["detail"] == "You must complete step 1 before step 3"
       assert data["next_required_step"] == 1
   ```

4. **No Performance Testing** - No slow query detection
5. **No Concurrency Testing** - Race conditions not tested
6. **Repetitive Code** - Same patterns copy-pasted

#### `test_repositories.py` - **Grade: C-**

**Problems:**

1. **Only Tests Happy Paths** - No constraint violation testing
   ```python
   # Missing tests:
   - Foreign key constraint violations
   - Unique constraint violations
   - NOT NULL constraint violations
   - Transaction rollback scenarios
   - Deadlock scenarios
   ```

2. **No Complex Query Testing** - Joins, aggregations not tested
   ```python
   # Missing:
   - Does get_all_passed_by_user handle 10,000 questions efficiently?
   - Are indexes being used correctly?
   - Are N+1 queries avoided?
   ```

3. **No Concurrent Operation Testing**
   ```python
   # Missing:
   async def test_concurrent_step_completions_handled_correctly(self):
       # Two users completing same step simultaneously
       # Should both succeed or one should fail gracefully
       pass
   ```

---

## Missing Test Categories

### 1. Service Layer Tests - **Grade: F (0% coverage)**

**Missing files:**
- `tests/test_services_llm.py` - LLM question evaluation
- `tests/test_services_github.py` - GitHub validation
- `tests/test_services_webhooks.py` - Webhook processing
- `tests/test_services_certificates.py` - Certificate generation
- `tests/test_services_dashboard.py` - Dashboard aggregation
- `tests/test_services_users.py` - User management

**Critical scenarios not tested:**
- LLM API failures (timeout, rate limit, invalid response)
- GitHub API failures (404, rate limit, network errors)
- Webhook signature validation
- Certificate SVG generation edge cases

### 2. Integration Tests - **Grade: F (None exist)**

**Missing end-to-end flows:**
- User signup → complete phase 0 → earn badge
- Submit GitHub repo → validate → unlock next phase
- Answer question → LLM evaluation → pass/fail → unlock
- Complete all phases → generate certificate → verify

### 3. Performance Tests - **Grade: F (None exist)**

**Missing benchmarks:**
- Dashboard load time with 1000 completed steps
- Question submission latency
- Concurrent user load (10, 100, 1000 users)
- Database query performance
- N+1 query detection

### 4. Security Tests - **Grade: F (None exist)**

**Missing tests:**
- SQL injection attempts
- XSS in question answers
- CSRF protection
- Rate limiting
- Authentication bypass attempts
- Authorization checks (user A accessing user B's data)

### 5. Error Handling Tests - **Grade: D**

**Barely tested scenarios:**
- Database connection failures
- External API timeouts (Clerk, GitHub, OpenAI)
- Malformed request bodies
- Invalid enum values
- Circular dependencies in data

---

## Test Metrics

| Category | Files | Tests (est) | Coverage | Grade |
|----------|-------|-------------|----------|-------|
| **Route Tests** | 1 | ~40 | Shallow | D |
| **Repository Tests** | 1 | ~40 | Basic CRUD | C- |
| **Progress/Badge Tests** | 2 | ~80 | Comprehensive | A |
| **Service Tests** | 0 | 0 | None | F |
| **Integration Tests** | 0 | 0 | None | F |
| **Performance Tests** | 0 | 0 | None | F |
| **Security Tests** | 0 | 0 | None | F |
| **Overall** | 4-5 | ~160 | ~30% | **D+** |

---

## Improvement Plan

### 🔴 Phase 1: Critical Fixes (High Priority)

#### 1. Improve `test_routes.py`

**Goal:** Transform from status code checks to comprehensive validation

**Tasks:**
- [ ] Add response schema validation for all endpoints
- [ ] Test edge cases (empty data, boundary values, invalid inputs)
- [ ] Add concurrent request testing
- [ ] Test error responses in detail
- [ ] Add authentication/authorization edge cases
- [ ] Test rate limiting (if implemented)

**Example improvements needed:**
```python
class TestStepEndpointsImproved:
    def test_complete_step_validates_response_schema(self, client):
        """Validates exact response structure, not just fields exist."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 1}
        )
        assert response.status_code == 200
        data = response.json()

        # Validate exact schema
        assert set(data.keys()) == {"topic_id", "step_order", "completed_at"}
        assert data["topic_id"] == "phase0-topic1"
        assert data["step_order"] == 1
        assert isinstance(data["completed_at"], str)
        # Validate ISO 8601 format
        datetime.fromisoformat(data["completed_at"].replace('Z', '+00:00'))

    def test_complete_step_concurrent_same_step(self, client):
        """Two concurrent requests to complete same step."""
        import asyncio

        async def complete():
            return client.post(
                "/api/steps/complete",
                json={"topic_id": "phase0-topic1", "step_order": 1}
            )

        # Both should get 200 first time, 400 second time
        results = await asyncio.gather(complete(), complete())
        status_codes = [r.status_code for r in results]
        assert status_codes.count(200) == 1
        assert status_codes.count(400) == 1

    def test_complete_step_sql_injection_attempt(self, client):
        """Ensures SQL injection is prevented."""
        response = client.post(
            "/api/steps/complete",
            json={
                "topic_id": "phase0-topic1'; DROP TABLE step_progress; --",
                "step_order": 1
            }
        )
        assert response.status_code == 400  # Validation should reject this
```

#### 2. Add Service Layer Tests

**Goal:** Test business logic in isolation

**Create:**
- `tests/test_services_llm.py`
- `tests/test_services_github.py`
- `tests/test_services_dashboard.py`
- `tests/test_services_certificates.py`

**Example:**
```python
# tests/test_services_llm.py
@pytest.mark.asyncio
class TestLLMQuestionEvaluation:
    async def test_evaluate_answer_success(self, mocker):
        """LLM returns positive evaluation."""
        mock_llm_response = {
            "is_passed": True,
            "feedback": "Great understanding of cloud concepts!"
        }
        mocker.patch("services.llm.call_openai", return_value=mock_llm_response)

        result = await evaluate_answer(
            question="What is cloud computing?",
            answer="Cloud computing provides on-demand resources..."
        )

        assert result.is_passed is True
        assert "understanding" in result.feedback

    async def test_evaluate_answer_handles_llm_timeout(self, mocker):
        """LLM timeout falls back gracefully."""
        mocker.patch(
            "services.llm.call_openai",
            side_effect=TimeoutError("API timeout")
        )

        result = await evaluate_answer(question="Q", answer="A")

        # Should either retry or return graceful failure
        assert result is not None
        assert hasattr(result, "is_passed")
```

#### 3. Add Critical Integration Tests

**Goal:** Test complete user flows

**Create:** `tests/test_integration.py`

```python
@pytest.mark.asyncio
@pytest.mark.integration
class TestCompletePhaseFlow:
    async def test_user_completes_phase_0_earns_badge(
        self,
        client,
        test_user,
        db_session
    ):
        """Complete user journey through Phase 0."""

        # 1. Complete all 15 steps
        for step in range(1, 16):
            response = client.post(
                "/api/steps/complete",
                json={"topic_id": "phase0-topic1", "step_order": step}
            )
            assert response.status_code == 200

        # 2. Pass all 12 questions
        for q in range(1, 13):
            response = client.post(
                "/api/questions/submit",
                json={
                    "topic_id": "phase0-topic1",
                    "question_id": f"phase0-topic1-q{q}",
                    "user_answer": "Detailed answer demonstrating understanding."
                }
            )
            assert response.status_code == 200
            assert response.json()["is_passed"] is True

        # 3. Submit GitHub profile
        response = client.post(
            "/api/github/submit",
            json={
                "requirement_id": "phase0-github-profile",
                "submitted_value": "https://github.com/testuser"
            }
        )
        assert response.status_code == 200

        # 4. Check dashboard shows phase complete + badge
        response = client.get("/api/user/dashboard")
        data = response.json()

        phase_0 = next(p for p in data["phases"] if p["id"] == 0)
        assert phase_0["progress"] == 100
        assert phase_0["is_complete"] is True

        badges = [b["id"] for b in data["badges"]]
        assert "phase_0_complete" in badges
```

---

### 🟡 Phase 2: Medium Priority

#### 4. Improve `test_repositories.py`

**Add:**
- Constraint violation tests
- Transaction rollback tests
- Concurrent operation tests
- Complex query performance tests

#### 5. Add Performance Tests

**Create:** `tests/test_performance.py`

```python
@pytest.mark.performance
class TestDashboardPerformance:
    def test_dashboard_loads_under_200ms_with_full_progress(self, client):
        """Dashboard should load quickly even with complete progress."""
        import time

        start = time.time()
        response = client.get("/api/user/dashboard")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 0.2  # Under 200ms
```

#### 6. Add Security Tests

**Create:** `tests/test_security.py`

```python
class TestAuthorizationBoundaries:
    def test_user_cannot_access_other_user_progress(self, client):
        """Users cannot view/modify other users' data."""
        # Create two users
        # User A tries to complete User B's step
        # Should get 403 Forbidden
        pass
```

---

### 🟢 Phase 3: Nice to Have

#### 7. Add Mutation Testing
Use `mutmut` to verify tests catch code changes

#### 8. Add Property-Based Testing
Use `hypothesis` for fuzz testing

#### 9. Add Contract Testing
Use Pact for API contract validation

---

## Specific Test Improvements Needed

### `test_routes.py` Improvements

#### Current Problems & Fixes:

| Test | Problem | Fix |
|------|---------|-----|
| `test_get_dashboard` | Only checks keys exist | Validate full schema, check data types, ranges |
| `test_complete_step` | Doesn't verify persistence | Read back step after completion |
| `test_submit_question_invalid_format` | Only checks 422, not error details | Validate error message structure |
| `test_public_profile_redacts_sensitive_submissions` | Uses asyncio directly | Use async test properly |

**Detailed Improvements:**

```python
# BEFORE (Bad):
def test_get_dashboard(self, client: TestClient):
    response = client.get("/api/user/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "phases" in data
    assert "badges" in data

# AFTER (Good):
def test_get_dashboard_structure(self, client: TestClient):
    """Dashboard returns correctly structured data."""
    response = client.get("/api/user/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Validate top-level structure
    required_keys = {
        "user", "phases", "overall_progress",
        "phases_completed", "phases_total",
        "current_phase", "badges"
    }
    assert set(data.keys()) == required_keys

    # Validate types
    assert isinstance(data["phases"], list)
    assert isinstance(data["badges"], list)
    assert isinstance(data["overall_progress"], (int, float))
    assert isinstance(data["phases_completed"], int)
    assert isinstance(data["phases_total"], int)

    # Validate ranges
    assert 0 <= data["overall_progress"] <= 100
    assert 0 <= data["phases_completed"] <= data["phases_total"]
    assert data["phases_total"] == 7  # Expected constant

    # Validate phase structure
    for phase in data["phases"]:
        assert "id" in phase
        assert "name" in phase
        assert "slug" in phase
        assert "progress" in phase
        assert "is_complete" in phase
        assert 0 <= phase["progress"] <= 100
        assert isinstance(phase["is_complete"], bool)

def test_get_dashboard_calculates_progress_correctly(
    self,
    client: TestClient,
    db_session: AsyncSession,
    test_user: User
):
    """Dashboard progress matches actual completion."""
    # Complete 1 step out of total 282 steps
    step_repo = StepProgressRepository(db_session)
    await step_repo.create(test_user.id, "phase0-topic1", 1)
    await db_session.commit()

    response = client.get("/api/user/dashboard")
    data = response.json()

    # Progress should be ~0.35% (1/282)
    expected_progress = (1 / 282) * 100
    assert abs(data["overall_progress"] - expected_progress) < 0.1
```

### `test_repositories.py` Improvements

```python
# ADD: Constraint testing
@pytest.mark.asyncio
class TestStepProgressConstraints:
    async def test_foreign_key_constraint_enforced(
        self,
        db_session: AsyncSession
    ):
        """Cannot create step for non-existent user."""
        repo = StepProgressRepository(db_session)

        with pytest.raises(IntegrityError):
            await repo.create(
                user_id="nonexistent_user",
                topic_id="phase0-topic1",
                step_order=1
            )
            await db_session.commit()

    async def test_unique_constraint_prevents_duplicates(
        self,
        db_session: AsyncSession,
        test_user: User
    ):
        """Cannot create duplicate step completion."""
        repo = StepProgressRepository(db_session)

        await repo.create(test_user.id, "phase0-topic1", 1)
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(test_user.id, "phase0-topic1", 1)
            await db_session.commit()

# ADD: Concurrent operation testing
@pytest.mark.asyncio
class TestConcurrentOperations:
    async def test_concurrent_step_completions_isolated(
        self,
        test_engine
    ):
        """Two sessions completing steps concurrently work correctly."""
        # Create two independent sessions
        session1 = async_sessionmaker(test_engine, class_=AsyncSession)()
        session2 = async_sessionmaker(test_engine, class_=AsyncSession)()

        try:
            repo1 = StepProgressRepository(session1)
            repo2 = StepProgressRepository(session2)

            # Both create steps concurrently
            await asyncio.gather(
                repo1.create("user1", "topic1", 1),
                repo2.create("user2", "topic1", 1),
            )

            await session1.commit()
            await session2.commit()

            # Both should succeed
            step1 = await repo1.get_completed_step_orders("user1", "topic1")
            step2 = await repo2.get_completed_step_orders("user2", "topic1")

            assert step1 == {1}
            assert step2 == {1}
        finally:
            await session1.close()
            await session2.close()
```

---

## Testing Best Practices to Adopt

### 1. AAA Pattern (Arrange-Act-Assert)

```python
def test_example(self):
    # Arrange - Set up test data
    user = create_test_user()
    topic_id = "phase0-topic1"

    # Act - Perform the action
    result = complete_step(user.id, topic_id, 1)

    # Assert - Verify the outcome
    assert result.is_completed is True
```

### 2. Test Naming Convention

```python
# Good naming:
def test_complete_step_requires_previous_steps_in_order()
def test_submit_question_rejects_answers_under_10_characters()
def test_dashboard_shows_zero_progress_for_new_users()

# Bad naming:
def test_step()
def test_question()
def test_works()
```

### 3. One Assertion Per Test (Generally)

```python
# Prefer this:
def test_dashboard_returns_200():
    response = client.get("/api/user/dashboard")
    assert response.status_code == 200

def test_dashboard_includes_phases():
    response = client.get("/api/user/dashboard")
    assert "phases" in response.json()

# Over this:
def test_dashboard():
    response = client.get("/api/user/dashboard")
    assert response.status_code == 200
    assert "phases" in response.json()
    assert len(response.json()["phases"]) == 7
    # ... 10 more assertions
```

### 4. Use Fixtures for Common Setup

```python
@pytest.fixture
def completed_phase_0_user(db_session, test_user):
    """User who has completed all of phase 0."""
    # Set up completed progress
    return test_user
```

### 5. Parameterize Repetitive Tests

```python
@pytest.mark.parametrize("phase_id,expected_steps", [
    (0, 15),
    (1, 36),
    (2, 30),
    (3, 31),
    (4, 51),
    (5, 55),
    (6, 64),
])
def test_phase_has_correct_step_count(phase_id, expected_steps):
    req = PHASE_REQUIREMENTS[phase_id]
    assert req.steps == expected_steps
```

---

## Recommended Tools

### Testing Frameworks
- ✅ **pytest** - Already in use
- ✅ **pytest-asyncio** - Already in use
- ⭕ **pytest-cov** - Add for coverage reports
- ⭕ **pytest-benchmark** - Add for performance testing
- ⭕ **pytest-xdist** - Add for parallel test execution

### Mocking & Fixtures
- ✅ **pytest fixtures** - Already in use
- ⭕ **pytest-mock** - Add for easier mocking
- ⭕ **responses** - Mock HTTP requests
- ⭕ **freezegun** - Mock datetime

### Property Testing
- ⭕ **hypothesis** - Property-based testing

### Load Testing
- ⭕ **locust** - Load testing framework
- ⭕ **pytest-benchmark** - Micro-benchmarks

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| **Test Count** | ~160 | 400+ |
| **Line Coverage** | ~30% | 80%+ |
| **Branch Coverage** | Unknown | 70%+ |
| **Avg Test Quality** | D+ | B+ |
| **Service Test Coverage** | 0% | 60%+ |
| **Integration Tests** | 0 | 20+ key flows |
| **Performance Tests** | 0 | 10+ benchmarks |
| **Security Tests** | 0 | 15+ scenarios |

---

## Priority Order

1. **Fix `test_routes.py`** - Improve existing shallow tests (2-3 days)
2. **Add service tests** - Test business logic (3-4 days)
3. **Add integration tests** - Test key flows (2-3 days)
4. **Improve `test_repositories.py`** - Add edge cases (1-2 days)
5. **Add performance tests** - Benchmark critical paths (1-2 days)
6. **Add security tests** - Test auth/authz (1-2 days)

**Total estimated effort: 2-3 weeks**

---

## Conclusion

The current API tests are **inadequate for production** but show some good patterns (badges, progress tests). The main issues are:

1. **Shallow coverage** - Tests verify too little
2. **Missing categories** - No service, integration, performance, or security tests
3. **Weak validation** - Assertions are too vague
4. **No edge cases** - Boundary conditions, errors, race conditions untested

**Recommendation:** Treat this as a **critical technical debt** that needs addressing before the next major release. Start with Phase 1 improvements (critical fixes) and work through systematically.

The good news: The test infrastructure (fixtures, database setup) is solid. We just need to write better tests using that infrastructure.
