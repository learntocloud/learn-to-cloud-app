"""Integration tests for repositories/progress_repository.py.

Uses real PostgreSQL database with transaction rollback for isolation.
Tests both StepProgressRepository and QuestionAttemptRepository.
"""

import pytest

from models import User
from repositories.progress_repository import (
    QuestionAttemptRepository,
    StepProgressRepository,
)


class TestStepProgressRepositoryIntegration:
    """Integration tests for StepProgressRepository."""

    async def _create_user(self, db, user_id: str = "test-user") -> User:
        """Helper to create a user."""
        user = User(
            id=user_id,
            email=f"{user_id}@example.com",
            first_name="Test",
            last_name="User",
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_create_step_progress(self, db_session):
        """create() creates a new step progress record."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        step = await repo.create(
            user_id="test-user",
            topic_id="phase0-topic1",
            step_order=1,
        )

        assert step.id is not None
        assert step.user_id == "test-user"
        assert step.topic_id == "phase0-topic1"
        assert step.step_order == 1

    @pytest.mark.asyncio
    async def test_get_by_user_and_topic(self, db_session):
        """get_by_user_and_topic returns steps ordered by step_order."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        # Create steps out of order
        await repo.create("test-user", "phase0-topic1", step_order=3)
        await repo.create("test-user", "phase0-topic1", step_order=1)
        await repo.create("test-user", "phase0-topic1", step_order=2)

        steps = await repo.get_by_user_and_topic("test-user", "phase0-topic1")

        assert len(steps) == 3
        assert steps[0].step_order == 1
        assert steps[1].step_order == 2
        assert steps[2].step_order == 3

    @pytest.mark.asyncio
    async def test_get_completed_step_orders(self, db_session):
        """get_completed_step_orders returns set of completed step numbers."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        await repo.create("test-user", "phase0-topic1", step_order=1)
        await repo.create("test-user", "phase0-topic1", step_order=3)
        await repo.create("test-user", "phase0-topic1", step_order=5)

        orders = await repo.get_completed_step_orders("test-user", "phase0-topic1")

        assert orders == {1, 3, 5}

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_exists(self, db_session):
        """exists() returns True when step is completed."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        await repo.create("test-user", "phase0-topic1", step_order=1)

        exists = await repo.exists("test-user", "phase0-topic1", step_order=1)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_not_exists(self, db_session):
        """exists() returns False when step not completed."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        exists = await repo.exists("test-user", "phase0-topic1", step_order=1)

        assert exists is False

    @pytest.mark.asyncio
    async def test_delete_from_step_cascades(self, db_session):
        """delete_from_step deletes step and all following steps."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        await repo.create("test-user", "phase0-topic1", step_order=1)
        await repo.create("test-user", "phase0-topic1", step_order=2)
        await repo.create("test-user", "phase0-topic1", step_order=3)
        await repo.create("test-user", "phase0-topic1", step_order=4)

        # Delete from step 2 onwards
        deleted = await repo.delete_from_step("test-user", "phase0-topic1", 2)

        assert deleted == 3  # Steps 2, 3, 4 deleted

        # Step 1 should still exist
        remaining = await repo.get_completed_step_orders("test-user", "phase0-topic1")
        assert remaining == {1}

    @pytest.mark.asyncio
    async def test_get_completed_step_topic_ids(self, db_session):
        """get_completed_step_topic_ids returns distinct topic IDs."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        await repo.create("test-user", "phase0-topic1", step_order=1)
        await repo.create("test-user", "phase0-topic1", step_order=2)
        await repo.create("test-user", "phase0-topic2", step_order=1)
        await repo.create("test-user", "phase1-topic1", step_order=1)

        topic_ids = await repo.get_completed_step_topic_ids("test-user")

        assert set(topic_ids) == {"phase0-topic1", "phase0-topic2", "phase1-topic1"}

    @pytest.mark.asyncio
    async def test_get_all_completed_by_user(self, db_session):
        """get_all_completed_by_user returns dict mapping topics to step orders."""
        await self._create_user(db_session)
        repo = StepProgressRepository(db_session)

        await repo.create("test-user", "phase0-topic1", step_order=1)
        await repo.create("test-user", "phase0-topic1", step_order=2)
        await repo.create("test-user", "phase0-topic2", step_order=1)

        by_topic = await repo.get_all_completed_by_user("test-user")

        assert by_topic["phase0-topic1"] == {1, 2}
        assert by_topic["phase0-topic2"] == {1}


class TestQuestionAttemptRepositoryIntegration:
    """Integration tests for QuestionAttemptRepository."""

    async def _create_user(self, db, user_id: str = "test-user") -> User:
        """Helper to create a user."""
        user = User(
            id=user_id,
            email=f"{user_id}@example.com",
            first_name="Test",
            last_name="User",
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_create_question_attempt(self, db_session):
        """create() creates a new question attempt record."""
        await self._create_user(db_session)
        repo = QuestionAttemptRepository(db_session)

        attempt = await repo.create(
            user_id="test-user",
            topic_id="phase0-topic1",
            question_id="phase0-topic1-q1",
            is_passed=True,
            user_answer="Cloud computing is...",
            llm_feedback="Good answer!",
            confidence_score=0.95,
        )

        assert attempt.id is not None
        assert attempt.is_passed is True
        assert attempt.confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_get_by_user_and_topic(self, db_session):
        """get_by_user_and_topic returns attempts ordered by created_at desc."""
        await self._create_user(db_session)
        repo = QuestionAttemptRepository(db_session)

        await repo.create("test-user", "phase0-topic1", "q1", is_passed=False)
        await repo.create("test-user", "phase0-topic1", "q1", is_passed=True)

        attempts = await repo.get_by_user_and_topic("test-user", "phase0-topic1")

        assert len(attempts) == 2
        # Most recent first
        assert attempts[0].is_passed is True

    @pytest.mark.asyncio
    async def test_get_passed_question_ids(self, db_session):
        """get_passed_question_ids returns only passed question IDs."""
        await self._create_user(db_session)
        repo = QuestionAttemptRepository(db_session)

        await repo.create("test-user", "phase0-topic1", "q1", is_passed=True)
        await repo.create("test-user", "phase0-topic1", "q2", is_passed=False)
        await repo.create("test-user", "phase0-topic1", "q3", is_passed=True)

        passed = await repo.get_passed_question_ids("test-user", "phase0-topic1")

        assert passed == {"q1", "q3"}

    @pytest.mark.asyncio
    async def test_get_all_passed_by_user(self, db_session):
        """get_all_passed_by_user returns dict mapping topics to passed question IDs."""
        await self._create_user(db_session)
        repo = QuestionAttemptRepository(db_session)

        await repo.create("test-user", "phase0-topic1", "q1", is_passed=True)
        await repo.create("test-user", "phase0-topic1", "q2", is_passed=True)
        await repo.create("test-user", "phase0-topic2", "q1", is_passed=True)
        await repo.create("test-user", "phase0-topic2", "q2", is_passed=False)

        by_topic = await repo.get_all_passed_by_user("test-user")

        assert by_topic["phase0-topic1"] == {"q1", "q2"}
        assert by_topic["phase0-topic2"] == {"q1"}

    @pytest.mark.asyncio
    async def test_get_all_passed_question_ids(self, db_session):
        """get_all_passed_question_ids returns distinct passed question IDs."""
        await self._create_user(db_session)
        repo = QuestionAttemptRepository(db_session)

        # Pass same question multiple times
        await repo.create("test-user", "phase0-topic1", "q1", is_passed=True)
        await repo.create("test-user", "phase0-topic1", "q1", is_passed=True)
        await repo.create("test-user", "phase0-topic2", "q2", is_passed=True)
        await repo.create("test-user", "phase0-topic2", "q3", is_passed=False)

        passed = await repo.get_all_passed_question_ids("test-user")

        assert set(passed) == {"q1", "q2"}

    @pytest.mark.asyncio
    async def test_isolation_between_users(self, db_session):
        """Question attempts are isolated between users."""
        await self._create_user(db_session, "user-1")
        await self._create_user(db_session, "user-2")
        repo = QuestionAttemptRepository(db_session)

        await repo.create("user-1", "phase0-topic1", "q1", is_passed=True)
        await repo.create("user-1", "phase0-topic1", "q2", is_passed=True)
        await repo.create("user-2", "phase0-topic1", "q1", is_passed=True)

        user1_passed = await repo.get_all_passed_question_ids("user-1")
        user2_passed = await repo.get_all_passed_question_ids("user-2")

        assert set(user1_passed) == {"q1", "q2"}
        assert set(user2_passed) == {"q1"}
