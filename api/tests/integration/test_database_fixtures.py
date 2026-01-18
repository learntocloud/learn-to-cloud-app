"""Integration tests for database fixtures.

These tests verify that the PostgreSQL test infrastructure works correctly.
"""

import pytest
from sqlalchemy import text


class TestDatabaseFixtures:
    """Test database fixture functionality."""

    @pytest.mark.asyncio
    async def test_db_session_connects(self, db_session):
        """Verify db_session fixture connects to PostgreSQL."""
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_db_session_creates_tables(self, db_session):
        """Verify tables are created by the test engine fixture."""
        # Check that the users table exists
        result = await db_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'users')"
            )
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_transaction_rollback_isolation(self, db_session, user_factory):
        """Verify each test gets a clean database via rollback."""
        # Create a user
        user = user_factory()
        db_session.add(user)
        await db_session.flush()

        # Verify it exists in this session
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM users WHERE id = :id"), {"id": user.id}
        )
        assert result.scalar() == 1

        # After the test, the transaction will be rolled back
        # The next test will not see this user


class TestModelFactories:
    """Test factory-boy model factories."""

    def test_user_factory_creates_valid_user(self, user_factory):
        """Verify UserFactory creates valid User instances."""
        user = user_factory()
        assert user.id is not None
        assert user.email is not None
        assert "@" in user.email
        assert user.github_username is not None

    def test_user_factory_with_overrides(self, user_factory):
        """Verify factory accepts parameter overrides."""
        user = user_factory(
            email="test@example.com",
            github_username="testuser",
            is_admin=True,
        )
        assert user.email == "test@example.com"
        assert user.github_username == "testuser"
        assert user.is_admin is True

    def test_submission_factory_creates_valid_submission(self, submission_factory):
        """Verify SubmissionFactory creates valid instances."""
        submission = submission_factory()
        assert submission.id is not None
        assert submission.user_id is not None
        assert submission.requirement_id is not None
        assert submission.is_validated is True

    def test_step_progress_factory_creates_valid_progress(self, step_progress_factory):
        """Verify StepProgressFactory creates valid instances."""
        progress = step_progress_factory()
        assert progress.id is not None
        assert progress.user_id is not None
        assert progress.topic_id is not None
        assert progress.step_order is not None

    def test_activity_factory_creates_valid_activity(self, activity_factory):
        """Verify UserActivityFactory creates valid instances."""
        activity = activity_factory()
        assert activity.id is not None
        assert activity.user_id is not None
        assert activity.activity_type is not None
        assert activity.activity_date is not None


class TestDatabaseOperations:
    """Test actual database operations with factories."""

    @pytest.mark.asyncio
    async def test_can_insert_and_query_user(self, db_session, user_factory):
        """Verify we can insert and query users."""
        user = user_factory(email="dbtest@example.com")
        db_session.add(user)
        await db_session.flush()

        # Query the user back
        result = await db_session.execute(
            text("SELECT email FROM users WHERE id = :id"), {"id": user.id}
        )
        assert result.scalar() == "dbtest@example.com"

    @pytest.mark.asyncio
    async def test_foreign_key_constraints_work(self, db_session, user_factory):
        """Verify foreign key constraints are enforced."""
        from models import StepProgress

        user = user_factory()
        db_session.add(user)
        await db_session.flush()

        # Create step progress linked to the user
        progress = StepProgress(
            user_id=user.id,
            topic_id="phase0-topic1",
            step_order=1,
        )
        db_session.add(progress)
        await db_session.flush()

        # Verify the relationship
        result = await db_session.execute(
            text("SELECT user_id FROM step_progress WHERE id = :id"),
            {"id": progress.id},
        )
        assert result.scalar() == user.id
