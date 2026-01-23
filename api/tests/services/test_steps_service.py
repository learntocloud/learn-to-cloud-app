"""Tests for steps service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration

from services.steps_service import (
    StepAlreadyCompletedError,
    StepInvalidStepOrderError,
    StepNotUnlockedError,
    StepUnknownTopicError,
    complete_step,
    get_topic_step_progress,
    uncomplete_step,
)
from tests.factories import StepProgressFactory, UserFactory


class TestGetTopicStepProgress:
    """Tests for get_topic_step_progress."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_returns_progress_for_valid_topic(
        self, db_session: AsyncSession, user
    ):
        """Test getting progress for a valid topic."""
        # Use a real topic ID from content
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        result = await get_topic_step_progress(db_session, user.id, topic.id)

        assert result.topic_id == topic.id
        assert result.completed_steps == []
        assert result.total_steps == len(topic.learning_steps)
        assert result.next_unlocked_step == 1

    async def test_raises_for_unknown_topic(self, db_session: AsyncSession, user):
        """Test that unknown topic ID raises StepUnknownTopicError."""
        with pytest.raises(StepUnknownTopicError):
            await get_topic_step_progress(db_session, user.id, "nonexistent-topic")

    async def test_returns_completed_steps(self, db_session: AsyncSession, user):
        """Test that completed steps are returned."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]
        if len(topic.learning_steps) < 2:
            pytest.skip("Topic needs at least 2 steps")

        # Complete first step
        step = StepProgressFactory.build(
            user_id=user.id, topic_id=topic.id, step_order=1
        )
        db_session.add(step)
        await db_session.flush()

        result = await get_topic_step_progress(db_session, user.id, topic.id)

        assert 1 in result.completed_steps
        assert result.next_unlocked_step == 2

    async def test_admin_unlocks_all_steps(self, db_session: AsyncSession, user):
        """Test that admin users have all steps unlocked."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        result = await get_topic_step_progress(
            db_session, user.id, topic.id, is_admin=True
        )

        # Admin should see next_unlocked_step as total_steps
        assert result.next_unlocked_step == result.total_steps


class TestCompleteStep:
    """Tests for complete_step."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_complete_first_step(self, db_session: AsyncSession, user):
        """Test completing the first step of a topic."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]
        if not topic.learning_steps:
            pytest.skip("Topic needs at least 1 step")

        result = await complete_step(db_session, user.id, topic.id, 1)

        assert result.topic_id == topic.id
        assert result.step_order == 1
        assert result.completed_at is not None

    async def test_complete_step_in_order(self, db_session: AsyncSession, user):
        """Test completing steps in sequential order."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]
        if len(topic.learning_steps) < 2:
            pytest.skip("Topic needs at least 2 steps")

        # Complete step 1
        await complete_step(db_session, user.id, topic.id, 1)

        # Complete step 2
        result = await complete_step(db_session, user.id, topic.id, 2)

        assert result.step_order == 2

    async def test_raises_for_already_completed_step(
        self, db_session: AsyncSession, user
    ):
        """Test that completing an already completed step raises error."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        # Complete step 1
        await complete_step(db_session, user.id, topic.id, 1)

        # Try to complete step 1 again
        with pytest.raises(StepAlreadyCompletedError):
            await complete_step(db_session, user.id, topic.id, 1)

    async def test_raises_for_out_of_order_step(self, db_session: AsyncSession, user):
        """Test that completing out of order raises StepNotUnlockedError."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]
        if len(topic.learning_steps) < 3:
            pytest.skip("Topic needs at least 3 steps")

        # Try to complete step 3 without completing 1 and 2
        with pytest.raises(StepNotUnlockedError):
            await complete_step(db_session, user.id, topic.id, 3)

    async def test_raises_for_unknown_topic(self, db_session: AsyncSession, user):
        """Test that unknown topic raises StepUnknownTopicError."""
        with pytest.raises(StepUnknownTopicError):
            await complete_step(db_session, user.id, "nonexistent-topic", 1)

    async def test_raises_for_invalid_step_order(self, db_session: AsyncSession, user):
        """Test that invalid step order raises StepInvalidStepOrderError."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        # Try to complete step 999
        with pytest.raises(StepInvalidStepOrderError):
            await complete_step(db_session, user.id, topic.id, 999)

    async def test_admin_can_skip_steps(self, db_session: AsyncSession, user):
        """Test that admin can complete any step regardless of order."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]
        if len(topic.learning_steps) < 3:
            pytest.skip("Topic needs at least 3 steps")

        # Admin should be able to complete step 3 directly
        result = await complete_step(db_session, user.id, topic.id, 3, is_admin=True)

        assert result.step_order == 3


class TestUncompleteStep:
    """Tests for uncomplete_step."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_uncomplete_step_removes_it(self, db_session: AsyncSession, user):
        """Test that uncompleting a step removes it."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        # Complete step 1
        await complete_step(db_session, user.id, topic.id, 1)

        # Uncomplete step 1
        deleted = await uncomplete_step(db_session, user.id, topic.id, 1)

        assert deleted == 1

    async def test_uncomplete_cascades_to_later_steps(
        self, db_session: AsyncSession, user
    ):
        """Test that uncompleting a step also removes later steps."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]
        if len(topic.learning_steps) < 3:
            pytest.skip("Topic needs at least 3 steps")

        # Complete steps 1, 2, 3
        await complete_step(db_session, user.id, topic.id, 1)
        await complete_step(db_session, user.id, topic.id, 2)
        await complete_step(db_session, user.id, topic.id, 3)

        # Uncomplete step 2 (should also remove step 3)
        deleted = await uncomplete_step(db_session, user.id, topic.id, 2)

        assert deleted == 2

    async def test_uncomplete_nonexistent_step_returns_zero(
        self, db_session: AsyncSession, user
    ):
        """Test that uncompleting a non-completed step returns 0."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        deleted = await uncomplete_step(db_session, user.id, topic.id, 1)

        assert deleted == 0

    async def test_raises_for_unknown_topic(self, db_session: AsyncSession, user):
        """Test that unknown topic raises StepUnknownTopicError."""
        with pytest.raises(StepUnknownTopicError):
            await uncomplete_step(db_session, user.id, "nonexistent-topic", 1)

    async def test_raises_for_invalid_step_order(self, db_session: AsyncSession, user):
        """Test that invalid step order raises StepInvalidStepOrderError."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        with pytest.raises(StepInvalidStepOrderError):
            await uncomplete_step(db_session, user.id, topic.id, 999)
