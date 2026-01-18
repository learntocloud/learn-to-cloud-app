"""Unit tests for services/users_service.py.

Tests user creation, profile lookup, and Clerk synchronization.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import SubmissionType
from services.users_service import (
    BadgeInfo,
    PublicProfileData,
    PublicSubmissionInfo,
    UserData,
    _is_placeholder_user,
    _needs_clerk_sync,
    _normalize_github_username,
    _to_user_data,
    get_or_create_user,
    get_public_profile,
)


class TestIsPlaceholderUser:
    """Test _is_placeholder_user helper."""

    def test_placeholder_email_returns_true(self):
        """Placeholder emails return True."""
        assert _is_placeholder_user("user_123@placeholder.local") is True
        assert _is_placeholder_user("anything@placeholder.local") is True

    def test_real_email_returns_false(self):
        """Real emails return False."""
        assert _is_placeholder_user("user@example.com") is False
        assert _is_placeholder_user("user@gmail.com") is False


class TestNeedsClerkSync:
    """Test _needs_clerk_sync helper."""

    def test_placeholder_email_needs_sync(self):
        """User with placeholder email needs sync."""
        user = MagicMock()
        user.email = "test@placeholder.local"
        user.avatar_url = "https://example.com/avatar.png"
        user.github_username = "testuser"
        assert _needs_clerk_sync(user) is True

    def test_missing_avatar_needs_sync(self):
        """User without avatar needs sync."""
        user = MagicMock()
        user.email = "real@example.com"
        user.avatar_url = None
        user.github_username = "testuser"
        assert _needs_clerk_sync(user) is True

    def test_missing_github_needs_sync(self):
        """User without GitHub username needs sync."""
        user = MagicMock()
        user.email = "real@example.com"
        user.avatar_url = "https://example.com/avatar.png"
        user.github_username = None
        assert _needs_clerk_sync(user) is True

    def test_complete_user_no_sync(self):
        """User with all data doesn't need sync."""
        user = MagicMock()
        user.email = "real@example.com"
        user.avatar_url = "https://example.com/avatar.png"
        user.github_username = "testuser"
        assert _needs_clerk_sync(user) is False


class TestNormalizeGithubUsername:
    """Test _normalize_github_username helper."""

    def test_normalizes_to_lowercase(self):
        """Username normalized to lowercase."""
        assert _normalize_github_username("TestUser") == "testuser"
        assert _normalize_github_username("UPPERCASE") == "uppercase"

    def test_already_lowercase(self):
        """Already lowercase stays lowercase."""
        assert _normalize_github_username("testuser") == "testuser"

    def test_none_returns_none(self):
        """None input returns None."""
        assert _normalize_github_username(None) is None

    def test_empty_string_returns_empty(self):
        """Empty string returns empty (falsy)."""
        assert _normalize_github_username("") is None


class TestToUserData:
    """Test _to_user_data conversion."""

    def test_converts_user_model_to_dto(self):
        """ORM User converted to UserData DTO."""
        now = datetime.now()
        user = MagicMock()
        user.id = "user-123"
        user.email = "test@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        user.avatar_url = "https://example.com/avatar.png"
        user.github_username = "testuser"
        user.is_admin = True
        user.created_at = now

        result = _to_user_data(user)

        assert isinstance(result, UserData)
        assert result.id == "user-123"
        assert result.email == "test@example.com"
        assert result.first_name == "Test"
        assert result.last_name == "User"
        assert result.avatar_url == "https://example.com/avatar.png"
        assert result.github_username == "testuser"
        assert result.is_admin is True
        assert result.created_at == now


class TestUserDataDataclass:
    """Test UserData dataclass behavior."""

    def test_is_frozen(self):
        """UserData is immutable (frozen)."""
        data = UserData(
            id="1",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            avatar_url=None,
            github_username=None,
            is_admin=False,
            created_at=datetime.now(),
        )
        with pytest.raises(AttributeError):
            data.email = "changed@example.com"  # type: ignore[misc]


class TestPublicSubmissionInfo:
    """Test PublicSubmissionInfo dataclass."""

    def test_creates_submission_info(self):
        """Can create submission info."""
        info = PublicSubmissionInfo(
            requirement_id="req-1",
            submission_type="GITHUB_REPO",
            phase_id=4,
            submitted_value="https://github.com/user/repo",
            name="Deploy a Web App",
            validated_at=datetime.now(),
        )
        assert info.requirement_id == "req-1"
        assert info.phase_id == 4


class TestBadgeInfo:
    """Test BadgeInfo dataclass."""

    def test_creates_badge_info(self):
        """Can create badge info."""
        badge = BadgeInfo(
            id="early-adopter",
            name="Early Adopter",
            description="Joined early",
            icon="🌟",
        )
        assert badge.id == "early-adopter"
        assert badge.icon == "🌟"


class TestGetOrCreateUser:
    """Test get_or_create_user async function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_existing_user(self, mock_db):
        """Returns existing user without Clerk sync if complete."""
        now = datetime.now()
        user = MagicMock()
        user.id = "user-123"
        user.email = "real@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        user.avatar_url = "https://example.com/avatar.png"
        user.github_username = "testuser"
        user.is_admin = False
        user.created_at = now
        user.updated_at = now

        with patch("services.users_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_or_create.return_value = user
            MockRepo.return_value = repo_instance

            result = await get_or_create_user(mock_db, "user-123")

        assert result.id == "user-123"
        assert result.email == "real@example.com"

    @pytest.mark.asyncio
    async def test_syncs_placeholder_user_from_clerk(self, mock_db):
        """Placeholder user syncs data from Clerk."""
        now = datetime.now()
        user = MagicMock()
        user.id = "user-123"
        user.email = "user_123@placeholder.local"
        user.first_name = None
        user.last_name = None
        user.avatar_url = None
        user.github_username = None
        user.is_admin = False
        user.created_at = now
        user.updated_at = now

        clerk_data = MagicMock()
        clerk_data.email = "real@example.com"
        clerk_data.first_name = "John"
        clerk_data.last_name = "Doe"
        clerk_data.avatar_url = "https://clerk.dev/avatar.png"
        clerk_data.github_username = "johndoe"

        with (
            patch("services.users_service.UserRepository") as MockRepo,
            patch("services.users_service.fetch_user_data") as mock_fetch,
        ):
            repo_instance = AsyncMock()
            repo_instance.get_or_create.return_value = user
            MockRepo.return_value = repo_instance
            mock_fetch.return_value = clerk_data

            await get_or_create_user(mock_db, "user-123")

        repo_instance.update.assert_called_once()
        # Check that normalized github username was passed
        call_kwargs = repo_instance.update.call_args.kwargs
        assert call_kwargs["github_username"] == "johndoe"

    @pytest.mark.asyncio
    async def test_tracks_new_user_metric(self, mock_db):
        """Logs metric for new user (created_at == updated_at)."""
        now = datetime.now()
        user = MagicMock()
        user.id = "new-user"
        user.email = "real@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        user.avatar_url = "https://example.com/avatar.png"
        user.github_username = "testuser"
        user.is_admin = False
        user.created_at = now
        user.updated_at = now  # Same as created_at = new user

        with (
            patch("services.users_service.UserRepository") as MockRepo,
            patch("services.users_service.log_metric") as mock_metric,
        ):
            repo_instance = AsyncMock()
            repo_instance.get_or_create.return_value = user
            MockRepo.return_value = repo_instance

            await get_or_create_user(mock_db, "new-user")

        mock_metric.assert_called_once_with("users.registered", 1)


class TestGetPublicProfile:
    """Test get_public_profile async function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_user(self, mock_db):
        """Returns None if user not found."""
        with (
            patch("services.users_service.UserRepository") as MockRepo,
            patch("services.users_service.SubmissionRepository"),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_by_github_username.return_value = None
            MockRepo.return_value = repo_instance

            result = await get_public_profile(mock_db, "unknown-user")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_complete_profile_data(self, mock_db):
        """Returns PublicProfileData with all fields."""
        now = datetime.now()
        user = MagicMock()
        user.id = "user-123"
        user.github_username = "testuser"
        user.first_name = "Test"
        user.avatar_url = "https://example.com/avatar.png"
        user.created_at = now

        mock_streak = MagicMock()
        mock_streak.current_streak = 5
        mock_streak.longest_streak = 10

        mock_heatmap = MagicMock()

        mock_progress = MagicMock()
        mock_progress.phases_completed = 2
        mock_progress.current_phase = 3

        with (
            patch("services.users_service.UserRepository") as MockUserRepo,
            patch("services.users_service.SubmissionRepository") as MockSubRepo,
            patch("services.users_service.get_streak_data", return_value=mock_streak),
            patch("services.users_service.get_heatmap_data", return_value=mock_heatmap),
            patch(
                "services.users_service.fetch_user_progress", return_value=mock_progress
            ),
            patch(
                "services.users_service.get_phase_completion_counts", return_value={}
            ),
            patch("services.users_service.compute_all_badges", return_value=[]),
        ):
            user_repo_instance = AsyncMock()
            user_repo_instance.get_by_github_username.return_value = user
            MockUserRepo.return_value = user_repo_instance

            sub_repo_instance = AsyncMock()
            sub_repo_instance.get_validated_by_user.return_value = []
            MockSubRepo.return_value = sub_repo_instance

            result = await get_public_profile(mock_db, "testuser")

        assert isinstance(result, PublicProfileData)
        assert result.username == "testuser"
        assert result.first_name == "Test"
        assert result.phases_completed == 2
        assert result.current_phase == 3

    @pytest.mark.asyncio
    async def test_redacts_sensitive_submissions(self, mock_db):
        """Sensitive submission types are redacted."""
        now = datetime.now()
        user = MagicMock()
        user.id = "user-123"
        user.github_username = "testuser"
        user.first_name = "Test"
        user.avatar_url = None
        user.created_at = now

        # Create mock submission with sensitive data
        sensitive_submission = MagicMock()
        sensitive_submission.requirement_id = "req-ctf"
        sensitive_submission.submission_type = SubmissionType.CTF_TOKEN
        sensitive_submission.phase_id = 2
        sensitive_submission.submitted_value = "secret-token-123"
        sensitive_submission.validated_at = now

        mock_requirement = MagicMock()
        mock_requirement.name = "CTF Challenge"

        mock_streak = MagicMock()
        mock_streak.longest_streak = 5
        mock_heatmap = MagicMock()
        mock_progress = MagicMock()
        mock_progress.phases_completed = 1
        mock_progress.current_phase = 2

        with (
            patch("services.users_service.UserRepository") as MockUserRepo,
            patch("services.users_service.SubmissionRepository") as MockSubRepo,
            patch("services.users_service.get_streak_data", return_value=mock_streak),
            patch("services.users_service.get_heatmap_data", return_value=mock_heatmap),
            patch(
                "services.users_service.fetch_user_progress", return_value=mock_progress
            ),
            patch(
                "services.users_service.get_phase_completion_counts", return_value={}
            ),
            patch("services.users_service.compute_all_badges", return_value=[]),
            patch(
                "services.users_service.get_requirement_by_id",
                return_value=mock_requirement,
            ),
        ):
            user_repo_instance = AsyncMock()
            user_repo_instance.get_by_github_username.return_value = user
            MockUserRepo.return_value = user_repo_instance

            sub_repo_instance = AsyncMock()
            sub_repo_instance.get_validated_by_user.return_value = [
                sensitive_submission
            ]
            MockSubRepo.return_value = sub_repo_instance

            result = await get_public_profile(mock_db, "testuser")

        # Sensitive value should be redacted
        assert result is not None
        assert len(result.submissions) == 1
        assert result.submissions[0].submitted_value == "[redacted]"

    @pytest.mark.asyncio
    async def test_includes_earned_badges(self, mock_db):
        """Profile includes computed badges."""
        now = datetime.now()
        user = MagicMock()
        user.id = "user-123"
        user.github_username = "testuser"
        user.first_name = "Test"
        user.avatar_url = None
        user.created_at = now

        mock_streak = MagicMock()
        mock_streak.longest_streak = 30

        mock_badge = MagicMock()
        mock_badge.id = "streak-master"
        mock_badge.name = "Streak Master"
        mock_badge.description = "30 day streak"
        mock_badge.icon = "🔥"

        mock_heatmap = MagicMock()
        mock_progress = MagicMock()
        mock_progress.phases_completed = 3
        mock_progress.current_phase = 4

        with (
            patch("services.users_service.UserRepository") as MockUserRepo,
            patch("services.users_service.SubmissionRepository") as MockSubRepo,
            patch("services.users_service.get_streak_data", return_value=mock_streak),
            patch("services.users_service.get_heatmap_data", return_value=mock_heatmap),
            patch(
                "services.users_service.fetch_user_progress", return_value=mock_progress
            ),
            patch(
                "services.users_service.get_phase_completion_counts", return_value={}
            ),
            patch(
                "services.users_service.compute_all_badges", return_value=[mock_badge]
            ),
        ):
            user_repo_instance = AsyncMock()
            user_repo_instance.get_by_github_username.return_value = user
            MockUserRepo.return_value = user_repo_instance

            sub_repo_instance = AsyncMock()
            sub_repo_instance.get_validated_by_user.return_value = []
            MockSubRepo.return_value = sub_repo_instance

            result = await get_public_profile(mock_db, "testuser")

        assert result is not None
        assert len(result.badges) == 1
        assert result.badges[0].id == "streak-master"
        assert result.badges[0].icon == "🔥"
