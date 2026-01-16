"""Repository layer tests.

Tests for database operations in the repository classes, ensuring
correct SQL queries and data persistence.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType, User
from repositories.progress import QuestionAttemptRepository, StepProgressRepository
from repositories.submission import SubmissionRepository
from repositories.user import UserRepository

# =============================================================================
# STEP PROGRESS REPOSITORY TESTS
# =============================================================================


@pytest.mark.asyncio
class TestStepProgressRepository:
    """Tests for StepProgressRepository database operations."""

    async def test_create_step_progress(
        self, db_session: AsyncSession, test_user: User
    ):
        """Create a new step progress record."""
        repo = StepProgressRepository(db_session)

        step = await repo.create(
            user_id=test_user.id,
            topic_id="phase0-topic0",
            step_order=1,
        )

        assert step.user_id == test_user.id
        assert step.topic_id == "phase0-topic0"
        assert step.step_order == 1
        assert step.id is not None

    async def test_exists_returns_true_for_completed_step(
        self, db_session: AsyncSession, test_user: User
    ):
        """exists() returns True for completed steps."""
        repo = StepProgressRepository(db_session)

        await repo.create(test_user.id, "phase0-topic0", 1)
        await db_session.commit()

        exists = await repo.exists(test_user.id, "phase0-topic0", 1)
        assert exists is True

    async def test_exists_returns_false_for_incomplete_step(
        self, db_session: AsyncSession, test_user: User
    ):
        """exists() returns False for steps not completed."""
        repo = StepProgressRepository(db_session)

        exists = await repo.exists(test_user.id, "phase0-topic0", 99)
        assert exists is False

    async def test_get_completed_step_orders(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_completed_step_orders returns set of completed steps."""
        repo = StepProgressRepository(db_session)

        await repo.create(test_user.id, "phase0-topic0", 1)
        await repo.create(test_user.id, "phase0-topic0", 2)
        await repo.create(test_user.id, "phase0-topic0", 3)
        await db_session.commit()

        orders = await repo.get_completed_step_orders(test_user.id, "phase0-topic0")
        assert orders == {1, 2, 3}

    async def test_get_by_user_and_topic(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_by_user_and_topic returns steps in order."""
        repo = StepProgressRepository(db_session)

        await repo.create(test_user.id, "phase0-topic0", 3)
        await repo.create(test_user.id, "phase0-topic0", 1)
        await repo.create(test_user.id, "phase0-topic0", 2)
        await db_session.commit()

        steps = await repo.get_by_user_and_topic(test_user.id, "phase0-topic0")
        assert len(steps) == 3
        assert [s.step_order for s in steps] == [1, 2, 3]  # Ordered

    async def test_delete_from_step_cascading(
        self, db_session: AsyncSession, test_user: User
    ):
        """delete_from_step removes step and all after it."""
        repo = StepProgressRepository(db_session)

        await repo.create(test_user.id, "phase0-topic0", 1)
        await repo.create(test_user.id, "phase0-topic0", 2)
        await repo.create(test_user.id, "phase0-topic0", 3)
        await repo.create(test_user.id, "phase0-topic0", 4)
        await db_session.commit()

        deleted_count = await repo.delete_from_step(test_user.id, "phase0-topic0", 3)
        await db_session.commit()

        assert deleted_count == 2  # Steps 3 and 4 deleted

        remaining = await repo.get_completed_step_orders(test_user.id, "phase0-topic0")
        assert remaining == {1, 2}

    async def test_count_by_phase(self, db_session: AsyncSession, test_user: User):
        """count_by_phase returns step counts per phase."""
        repo = StepProgressRepository(db_session)

        # Add steps to phase 0
        await repo.create(test_user.id, "phase0-topic0", 1)
        await repo.create(test_user.id, "phase0-topic0", 2)
        await repo.create(test_user.id, "phase0-topic1", 1)
        # Add steps to phase 1
        await repo.create(test_user.id, "phase1-topic0", 1)
        await db_session.commit()

        counts = await repo.count_by_phase(test_user.id)

        assert counts[0] == 3  # 3 steps in phase 0
        assert counts[1] == 1  # 1 step in phase 1


# =============================================================================
# QUESTION ATTEMPT REPOSITORY TESTS
# =============================================================================


@pytest.mark.asyncio
class TestQuestionAttemptRepository:
    """Tests for QuestionAttemptRepository database operations."""

    async def test_create_question_attempt(
        self, db_session: AsyncSession, test_user: User
    ):
        """Create a new question attempt."""
        repo = QuestionAttemptRepository(db_session)

        attempt = await repo.create(
            user_id=test_user.id,
            topic_id="phase0-topic0",
            question_id="phase0-topic0-q1",
            is_passed=True,
            user_answer="My answer",
        )

        assert attempt.user_id == test_user.id
        assert attempt.question_id == "phase0-topic0-q1"
        assert attempt.is_passed is True

    async def test_get_passed_question_ids(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_passed_question_ids returns only passed questions."""
        repo = QuestionAttemptRepository(db_session)

        await repo.create(test_user.id, "phase0-topic0", "q1", is_passed=True)
        await repo.create(test_user.id, "phase0-topic0", "q2", is_passed=False)
        await repo.create(test_user.id, "phase0-topic0", "q3", is_passed=True)
        await db_session.commit()

        passed = await repo.get_passed_question_ids(test_user.id, "phase0-topic0")
        assert passed == {"q1", "q3"}

    async def test_get_all_passed_by_user(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_all_passed_by_user returns passed questions grouped by topic."""
        repo = QuestionAttemptRepository(db_session)

        await repo.create(test_user.id, "phase0-topic0", "q1", is_passed=True)
        await repo.create(test_user.id, "phase0-topic0", "q2", is_passed=True)
        await repo.create(test_user.id, "phase1-topic0", "q1", is_passed=True)
        await repo.create(test_user.id, "phase1-topic0", "q2", is_passed=False)
        await db_session.commit()

        all_passed = await repo.get_all_passed_by_user(test_user.id)

        assert "phase0-topic0" in all_passed
        assert "phase1-topic0" in all_passed
        assert all_passed["phase0-topic0"] == {"q1", "q2"}
        assert all_passed["phase1-topic0"] == {"q1"}

    async def test_count_passed_by_phase(
        self, db_session: AsyncSession, test_user: User
    ):
        """count_passed_by_phase returns passed question counts per phase."""
        repo = QuestionAttemptRepository(db_session)

        await repo.create(
            test_user.id, "phase0-topic0", "phase0-topic0-q1", is_passed=True
        )
        await repo.create(
            test_user.id, "phase0-topic0", "phase0-topic0-q2", is_passed=True
        )
        await repo.create(
            test_user.id, "phase1-topic0", "phase1-topic0-q1", is_passed=True
        )
        await db_session.commit()

        counts = await repo.count_passed_by_phase(test_user.id)

        assert counts[0] == 2  # 2 passed in phase 0
        assert counts[1] == 1  # 1 passed in phase 1


# =============================================================================
# SUBMISSION REPOSITORY TESTS
# =============================================================================


@pytest.mark.asyncio
class TestSubmissionRepository:
    """Tests for SubmissionRepository database operations."""

    async def test_upsert_creates_new_submission(
        self, db_session: AsyncSession, test_user: User
    ):
        """upsert creates a new submission when none exists."""
        repo = SubmissionRepository(db_session)

        submission = await repo.upsert(
            user_id=test_user.id,
            requirement_id="phase0-github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )
        await db_session.commit()

        assert submission.user_id == test_user.id
        assert submission.requirement_id == "phase0-github-profile"
        assert submission.is_validated is True

    async def test_upsert_updates_existing_submission(
        self, db_session: AsyncSession, test_user: User
    ):
        """upsert updates an existing submission."""
        repo = SubmissionRepository(db_session)

        # Create initial submission
        await repo.upsert(
            user_id=test_user.id,
            requirement_id="phase0-github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/olduser",
            extracted_username="olduser",
            is_validated=False,
        )
        await db_session.commit()

        # Update with new value
        submission = await repo.upsert(
            user_id=test_user.id,
            requirement_id="phase0-github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/newuser",
            extracted_username="newuser",
            is_validated=True,
        )
        await db_session.commit()

        assert submission.submitted_value == "https://github.com/newuser"
        assert submission.is_validated is True

    async def test_get_by_user_and_requirement(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_by_user_and_requirement returns correct submission."""
        repo = SubmissionRepository(db_session)

        await repo.upsert(
            user_id=test_user.id,
            requirement_id="phase0-github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )
        await db_session.commit()

        submission = await repo.get_by_user_and_requirement(
            test_user.id, "phase0-github-profile"
        )

        assert submission is not None
        assert submission.requirement_id == "phase0-github-profile"

    async def test_get_by_user_and_requirement_returns_none(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_by_user_and_requirement returns None for non-existent."""
        repo = SubmissionRepository(db_session)

        submission = await repo.get_by_user_and_requirement(test_user.id, "nonexistent")

        assert submission is None

    async def test_get_all_by_user(self, db_session: AsyncSession, test_user: User):
        """get_all_by_user returns all user submissions."""
        repo = SubmissionRepository(db_session)

        await repo.upsert(
            test_user.id,
            "req1",
            SubmissionType.GITHUB_PROFILE,
            0,
            "https://github.com/test1",
            "test1",
            True,
        )
        await repo.upsert(
            test_user.id,
            "req2",
            SubmissionType.REPO_URL,
            1,
            "https://github.com/test2/repo",
            "test2",
            True,
        )
        await db_session.commit()

        submissions = await repo.get_all_by_user(test_user.id)

        assert len(submissions) == 2

    async def test_get_by_user_and_phase(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_by_user_and_phase returns only submissions for that phase."""
        repo = SubmissionRepository(db_session)

        await repo.upsert(
            test_user.id,
            "req1",
            SubmissionType.GITHUB_PROFILE,
            0,
            "https://github.com/test1",
            "test1",
            True,
        )
        await repo.upsert(
            test_user.id,
            "req2",
            SubmissionType.REPO_URL,
            1,
            "https://github.com/test2/repo",
            "test2",
            True,
        )
        await db_session.commit()

        phase0_submissions = await repo.get_by_user_and_phase(test_user.id, 0)
        phase1_submissions = await repo.get_by_user_and_phase(test_user.id, 1)

        assert len(phase0_submissions) == 1
        assert len(phase1_submissions) == 1

    async def test_get_validated_by_user(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_validated_by_user returns only validated submissions."""
        repo = SubmissionRepository(db_session)

        await repo.upsert(
            test_user.id,
            "req1",
            SubmissionType.GITHUB_PROFILE,
            0,
            "https://github.com/test1",
            "test1",
            True,  # Validated
        )
        await repo.upsert(
            test_user.id,
            "req2",
            SubmissionType.REPO_URL,
            1,
            "https://github.com/test2/repo",
            "test2",
            False,  # Not validated
        )
        await db_session.commit()

        validated = await repo.get_validated_by_user(test_user.id)

        assert len(validated) == 1
        assert validated[0].requirement_id == "req1"


# =============================================================================
# USER REPOSITORY TESTS
# =============================================================================


@pytest.mark.asyncio
class TestUserRepository:
    """Tests for UserRepository database operations."""

    async def test_get_by_id(self, db_session: AsyncSession, test_user: User):
        """get_by_id returns user by ID."""
        repo = UserRepository(db_session)

        user = await repo.get_by_id(test_user.id)

        assert user is not None
        assert user.id == test_user.id

    async def test_get_by_id_returns_none(self, db_session: AsyncSession):
        """get_by_id returns None for non-existent user."""
        repo = UserRepository(db_session)

        user = await repo.get_by_id("nonexistent_user_id")

        assert user is None

    async def test_get_by_github_username(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_by_github_username returns user by GitHub username."""
        repo = UserRepository(db_session)

        assert test_user.github_username is not None
        user = await repo.get_by_github_username(test_user.github_username)

        assert user is not None
        assert user.github_username == test_user.github_username

    async def test_get_or_create_existing_user(
        self, db_session: AsyncSession, test_user: User
    ):
        """get_or_create returns existing user without creating new one."""
        repo = UserRepository(db_session)

        user = await repo.get_or_create(test_user.id)

        assert user.id == test_user.id
        assert user.email == test_user.email  # Not placeholder

    async def test_get_or_create_new_user(self, db_session: AsyncSession):
        """get_or_create creates placeholder for new user."""
        repo = UserRepository(db_session)

        user = await repo.get_or_create("new_user_123")
        await db_session.commit()

        assert user.id == "new_user_123"
        assert "placeholder" in user.email

    async def test_create_user(self, db_session: AsyncSession):
        """create creates a new user with all fields."""
        repo = UserRepository(db_session)

        user = await repo.create(
            user_id="new_user_456",
            email="new@example.com",
            first_name="New",
            last_name="User",
            github_username="newuser",
        )
        await db_session.commit()

        assert user.id == "new_user_456"
        assert user.email == "new@example.com"
        assert user.first_name == "New"
        assert user.github_username == "newuser"


# =============================================================================
# REPOSITORY ISOLATION TESTS
# =============================================================================


@pytest.mark.asyncio
class TestRepositoryIsolation:
    """Tests ensuring repositories work with isolated transactions."""

    async def test_different_users_isolated(self, db_session: AsyncSession):
        """Different users have isolated data."""
        # Create two users
        user1 = User(id="user1", email="user1@test.com")
        user2 = User(id="user2", email="user2@test.com")
        db_session.add(user1)
        db_session.add(user2)
        await db_session.commit()

        step_repo = StepProgressRepository(db_session)

        await step_repo.create("user1", "phase0-topic0", 1)
        await step_repo.create("user1", "phase0-topic0", 2)
        await step_repo.create("user2", "phase0-topic0", 1)
        await db_session.commit()

        user1_steps = await step_repo.get_completed_step_orders(
            "user1", "phase0-topic0"
        )
        user2_steps = await step_repo.get_completed_step_orders(
            "user2", "phase0-topic0"
        )

        assert user1_steps == {1, 2}
        assert user2_steps == {1}

    async def test_different_topics_isolated(
        self, db_session: AsyncSession, test_user: User
    ):
        """Different topics have isolated data."""
        step_repo = StepProgressRepository(db_session)

        await step_repo.create(test_user.id, "phase0-topic0", 1)
        await step_repo.create(test_user.id, "phase0-topic0", 2)
        await step_repo.create(test_user.id, "phase0-topic1", 1)
        await db_session.commit()

        topic0_steps = await step_repo.get_completed_step_orders(
            test_user.id, "phase0-topic0"
        )
        topic1_steps = await step_repo.get_completed_step_orders(
            test_user.id, "phase0-topic1"
        )

        assert topic0_steps == {1, 2}
        assert topic1_steps == {1}
