"""Tests for StepProgressRepository and QuestionAttemptRepository.

Tests database operations for learning progress tracking.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.progress_repository import (
    QuestionAttemptRepository,
    StepProgressRepository,
)
from tests.factories import (
    FailedQuestionAttemptFactory,
    QuestionAttemptFactory,
    StepProgressFactory,
    UserFactory,
    create_async,
)


# =============================================================================
# StepProgressRepository Tests
# =============================================================================


class TestStepProgressRepositoryGetByUserAndTopic:
    """Tests for StepProgressRepository.get_by_user_and_topic()."""

    async def test_returns_steps_for_user_and_topic(self, db_session: AsyncSession):
        """Should return all completed steps for user in topic."""
        user = await create_async(UserFactory, db_session)
        step1 = await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )
        step2 = await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=2,
        )
        # Different topic - should not be included
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic2",
            step_order=1,
        )

        repo = StepProgressRepository(db_session)

        result = await repo.get_by_user_and_topic(user.id, "phase1-topic1")

        assert len(result) == 2
        result_orders = [s.step_order for s in result]
        assert 1 in result_orders
        assert 2 in result_orders

    async def test_returns_empty_when_no_progress(self, db_session: AsyncSession):
        """Should return empty list when no progress exists."""
        user = await create_async(UserFactory, db_session)
        repo = StepProgressRepository(db_session)

        result = await repo.get_by_user_and_topic(user.id, "phase1-topic1")

        assert result == []

    async def test_orders_by_step_order(self, db_session: AsyncSession):
        """Should return steps ordered by step_order."""
        user = await create_async(UserFactory, db_session)
        # Create in reverse order
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=3,
        )
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )

        repo = StepProgressRepository(db_session)

        result = await repo.get_by_user_and_topic(user.id, "phase1-topic1")

        assert [s.step_order for s in result] == [1, 3]


class TestStepProgressRepositoryGetCompletedStepOrders:
    """Tests for StepProgressRepository.get_completed_step_orders()."""

    async def test_returns_set_of_completed_step_orders(
        self, db_session: AsyncSession
    ):
        """Should return set of completed step orders."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=3,
        )

        repo = StepProgressRepository(db_session)

        result = await repo.get_completed_step_orders(user.id, "phase1-topic1")

        assert result == {1, 3}


class TestStepProgressRepositoryExists:
    """Tests for StepProgressRepository.exists()."""

    async def test_returns_true_when_step_completed(self, db_session: AsyncSession):
        """Should return True when step is completed."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )

        repo = StepProgressRepository(db_session)

        result = await repo.exists(user.id, "phase1-topic1", step_order=1)

        assert result is True

    async def test_returns_false_when_step_not_completed(
        self, db_session: AsyncSession
    ):
        """Should return False when step is not completed."""
        user = await create_async(UserFactory, db_session)
        repo = StepProgressRepository(db_session)

        result = await repo.exists(user.id, "phase1-topic1", step_order=1)

        assert result is False


class TestStepProgressRepositoryCreate:
    """Tests for StepProgressRepository.create()."""

    async def test_creates_step_progress(self, db_session: AsyncSession):
        """Should create a new step progress record."""
        user = await create_async(UserFactory, db_session)
        repo = StepProgressRepository(db_session)

        step = await repo.create(user.id, "phase1-topic1", step_order=1)

        assert step.user_id == user.id
        assert step.topic_id == "phase1-topic1"
        assert step.step_order == 1
        assert step.completed_at is not None


class TestStepProgressRepositoryDeleteFromStep:
    """Tests for StepProgressRepository.delete_from_step()."""

    async def test_deletes_step_and_following(self, db_session: AsyncSession):
        """Should delete specified step and all following steps."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=2,
        )
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=3,
        )

        repo = StepProgressRepository(db_session)

        deleted_count = await repo.delete_from_step(user.id, "phase1-topic1", 2)
        await db_session.flush()

        assert deleted_count == 2

        remaining = await repo.get_completed_step_orders(user.id, "phase1-topic1")
        assert remaining == {1}


class TestStepProgressRepositoryGetAllCompletedByUser:
    """Tests for StepProgressRepository.get_all_completed_by_user()."""

    async def test_returns_steps_grouped_by_topic(self, db_session: AsyncSession):
        """Should return all completed steps grouped by topic."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            step_order=2,
        )
        await create_async(
            StepProgressFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic2",
            step_order=1,
        )

        repo = StepProgressRepository(db_session)

        result = await repo.get_all_completed_by_user(user.id)

        assert result == {
            "phase1-topic1": {1, 2},
            "phase1-topic2": {1},
        }


# =============================================================================
# QuestionAttemptRepository Tests
# =============================================================================


class TestQuestionAttemptRepositoryGetByUserAndTopic:
    """Tests for QuestionAttemptRepository.get_by_user_and_topic()."""

    async def test_returns_attempts_for_user_and_topic(
        self, db_session: AsyncSession
    ):
        """Should return all attempts for user in topic."""
        user = await create_async(UserFactory, db_session)
        attempt1 = await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
        )
        attempt2 = await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q2",
        )
        # Different topic
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic2",
        )

        repo = QuestionAttemptRepository(db_session)

        result = await repo.get_by_user_and_topic(user.id, "phase1-topic1")

        assert len(result) == 2


class TestQuestionAttemptRepositoryGetPassedQuestionIds:
    """Tests for QuestionAttemptRepository.get_passed_question_ids()."""

    async def test_returns_only_passed_question_ids(self, db_session: AsyncSession):
        """Should return only IDs of passed questions."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
        )
        await create_async(
            FailedQuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q2",
        )

        repo = QuestionAttemptRepository(db_session)

        result = await repo.get_passed_question_ids(user.id, "phase1-topic1")

        assert result == {"phase1-topic1-q1"}

    async def test_returns_distinct_ids(self, db_session: AsyncSession):
        """Should return distinct question IDs (even with multiple attempts)."""
        user = await create_async(UserFactory, db_session)
        # Multiple attempts on same question
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
        )
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
        )

        repo = QuestionAttemptRepository(db_session)

        result = await repo.get_passed_question_ids(user.id, "phase1-topic1")

        assert result == {"phase1-topic1-q1"}


class TestQuestionAttemptRepositoryGetAllPassedByUser:
    """Tests for QuestionAttemptRepository.get_all_passed_by_user()."""

    async def test_returns_passed_grouped_by_topic(self, db_session: AsyncSession):
        """Should return passed questions grouped by topic."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
        )
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q2",
            is_passed=True,
        )
        await create_async(
            QuestionAttemptFactory,
            db_session,
            user_id=user.id,
            topic_id="phase1-topic2",
            question_id="phase1-topic2-q1",
            is_passed=True,
        )

        repo = QuestionAttemptRepository(db_session)

        result = await repo.get_all_passed_by_user(user.id)

        assert result == {
            "phase1-topic1": {"phase1-topic1-q1", "phase1-topic1-q2"},
            "phase1-topic2": {"phase1-topic2-q1"},
        }


class TestQuestionAttemptRepositoryCreate:
    """Tests for QuestionAttemptRepository.create()."""

    async def test_creates_passed_attempt(self, db_session: AsyncSession):
        """Should create a passed question attempt."""
        user = await create_async(UserFactory, db_session)
        repo = QuestionAttemptRepository(db_session)

        attempt = await repo.create(
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
            user_answer="My answer explaining cloud concepts...",
            llm_feedback="Great explanation!",
            confidence_score=0.95,
        )

        assert attempt.user_id == user.id
        assert attempt.is_passed is True
        assert attempt.confidence_score == 0.95

    async def test_creates_failed_attempt(self, db_session: AsyncSession):
        """Should create a failed question attempt."""
        user = await create_async(UserFactory, db_session)
        repo = QuestionAttemptRepository(db_session)

        attempt = await repo.create(
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=False,
            user_answer="Incorrect answer...",
            llm_feedback="Please review the concepts.",
            confidence_score=0.3,
        )

        assert attempt.is_passed is False
        assert attempt.llm_feedback == "Please review the concepts."
