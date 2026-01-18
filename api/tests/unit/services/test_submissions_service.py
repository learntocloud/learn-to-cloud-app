"""Unit tests for services/submissions_service.py.

Tests submission data transformation, validation flow, and error handling.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import SubmissionType
from services.submissions_service import (
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    SubmissionData,
    SubmissionResult,
    _to_submission_data,
    get_validated_ids_by_phase,
    submit_validation,
)


class TestSubmissionData:
    """Test SubmissionData dataclass."""

    def test_is_frozen(self):
        """SubmissionData is immutable."""
        now = datetime.now()
        data = SubmissionData(
            id=1,
            requirement_id="req-1",
            submission_type=SubmissionType.REPO_URL,
            phase_id=4,
            submitted_value="https://github.com/user/repo",
            extracted_username="user",
            is_validated=True,
            validated_at=now,
            created_at=now,
        )
        with pytest.raises(AttributeError):
            data.is_validated = False  # type: ignore[misc]

    def test_create_with_all_fields(self):
        """Can create with all required fields."""
        now = datetime.now()
        data = SubmissionData(
            id=1,
            requirement_id="req-1",
            submission_type=SubmissionType.REPO_URL,
            phase_id=4,
            submitted_value="https://github.com/user/repo",
            extracted_username="user",
            is_validated=True,
            validated_at=now,
            created_at=now,
        )
        assert data.id == 1
        assert data.requirement_id == "req-1"


class TestToSubmissionData:
    """Test _to_submission_data conversion."""

    def test_converts_orm_model_to_dto(self):
        """ORM Submission converted to SubmissionData DTO."""
        now = datetime.now()
        submission = MagicMock()
        submission.id = 42
        submission.requirement_id = "req-deploy-1"
        submission.submission_type = SubmissionType.DEPLOYED_APP
        submission.phase_id = 4
        submission.submitted_value = "https://myapp.azurewebsites.net"
        submission.extracted_username = None
        submission.is_validated = True
        submission.validated_at = now
        submission.created_at = now

        result = _to_submission_data(submission)

        assert isinstance(result, SubmissionData)
        assert result.id == 42
        assert result.requirement_id == "req-deploy-1"
        assert result.submission_type == SubmissionType.DEPLOYED_APP
        assert result.phase_id == 4
        assert result.is_validated is True


class TestGetValidatedIdsByPhase:
    """Test get_validated_ids_by_phase helper."""

    def test_groups_validated_by_phase(self):
        """Groups validated requirement IDs by phase."""
        sub1 = MagicMock()
        sub1.phase_id = 4
        sub1.requirement_id = "req-1"
        sub1.is_validated = True

        sub2 = MagicMock()
        sub2.phase_id = 4
        sub2.requirement_id = "req-2"
        sub2.is_validated = True

        sub3 = MagicMock()
        sub3.phase_id = 5
        sub3.requirement_id = "req-3"
        sub3.is_validated = True

        result = get_validated_ids_by_phase([sub1, sub2, sub3])

        assert result[4] == {"req-1", "req-2"}
        assert result[5] == {"req-3"}

    def test_excludes_invalid_submissions(self):
        """Non-validated submissions excluded."""
        validated = MagicMock()
        validated.phase_id = 4
        validated.requirement_id = "req-1"
        validated.is_validated = True

        not_validated = MagicMock()
        not_validated.phase_id = 4
        not_validated.requirement_id = "req-2"
        not_validated.is_validated = False

        result = get_validated_ids_by_phase([validated, not_validated])

        assert result[4] == {"req-1"}

    def test_empty_list_returns_empty_dict(self):
        """Empty input returns empty dict."""
        result = get_validated_ids_by_phase([])
        assert result == {}


class TestSubmissionResult:
    """Test SubmissionResult dataclass."""

    def test_create_result(self):
        """Can create a submission result."""
        now = datetime.now()
        sub_data = SubmissionData(
            id=1,
            requirement_id="req-1",
            submission_type=SubmissionType.REPO_URL,
            phase_id=4,
            submitted_value="https://github.com/user/repo",
            extracted_username="user",
            is_validated=True,
            validated_at=now,
            created_at=now,
        )
        result = SubmissionResult(
            submission=sub_data,
            is_valid=True,
            message="Repository validated successfully",
            username_match=True,
            repo_exists=True,
        )
        assert result.is_valid is True
        assert result.username_match is True


class TestRequirementNotFoundError:
    """Test RequirementNotFoundError exception."""

    def test_raises_with_message(self):
        """Exception includes requirement ID in message."""
        with pytest.raises(RequirementNotFoundError, match="req-unknown"):
            raise RequirementNotFoundError("Requirement not found: req-unknown")


class TestGitHubUsernameRequiredError:
    """Test GitHubUsernameRequiredError exception."""

    def test_raises_with_message(self):
        """Exception includes helpful message."""
        with pytest.raises(GitHubUsernameRequiredError, match="link your GitHub"):
            raise GitHubUsernameRequiredError(
                "You need to link your GitHub account to submit."
            )


class TestSubmitValidation:
    """Test submit_validation async function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_raises_on_unknown_requirement(self, mock_db):
        """Raises RequirementNotFoundError for unknown requirement."""
        with (
            patch(
                "services.submissions_service.get_requirement_by_id", return_value=None
            ),
            patch("services.submissions_service.add_custom_attribute"),
        ):
            with pytest.raises(RequirementNotFoundError):
                await submit_validation(
                    mock_db,
                    user_id="user-1",
                    requirement_id="unknown-req",
                    submitted_value="https://example.com",
                    github_username="testuser",
                )

    @pytest.mark.asyncio
    async def test_raises_on_missing_github_for_profile_readme(self, mock_db):
        """Raises GitHubUsernameRequiredError for PROFILE_README without username."""
        requirement = MagicMock()
        requirement.submission_type = SubmissionType.PROFILE_README

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
        ):
            with pytest.raises(GitHubUsernameRequiredError):
                await submit_validation(
                    mock_db,
                    user_id="user-1",
                    requirement_id="profile-readme",
                    submitted_value="https://github.com/user",
                    github_username=None,  # Missing!
                )

    @pytest.mark.asyncio
    async def test_raises_on_missing_github_for_repo_fork(self, mock_db):
        """Raises GitHubUsernameRequiredError for REPO_FORK without username."""
        requirement = MagicMock()
        requirement.submission_type = SubmissionType.REPO_FORK

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
        ):
            with pytest.raises(GitHubUsernameRequiredError):
                await submit_validation(
                    mock_db,
                    user_id="user-1",
                    requirement_id="repo-fork",
                    submitted_value="https://github.com/user/repo",
                    github_username=None,
                )

    @pytest.mark.asyncio
    async def test_raises_on_missing_github_for_ctf_token(self, mock_db):
        """Raises GitHubUsernameRequiredError for CTF_TOKEN without username."""
        requirement = MagicMock()
        requirement.submission_type = SubmissionType.CTF_TOKEN

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
        ):
            with pytest.raises(GitHubUsernameRequiredError):
                await submit_validation(
                    mock_db,
                    user_id="user-1",
                    requirement_id="ctf-challenge",
                    submitted_value="token123",
                    github_username=None,
                )

    @pytest.mark.asyncio
    async def test_successful_validation_saves_submission(self, mock_db):
        """Valid submission is saved and returned."""
        now = datetime.now()

        requirement = MagicMock()
        requirement.submission_type = SubmissionType.REPO_URL
        requirement.phase_id = 4

        validation_result = MagicMock()
        validation_result.is_valid = True
        validation_result.message = "Repository validated"
        validation_result.username_match = True
        validation_result.repo_exists = True

        parsed_url = MagicMock()
        parsed_url.is_valid = True
        parsed_url.username = "testuser"

        db_submission = MagicMock()
        db_submission.id = 1
        db_submission.requirement_id = "deploy-webapp"
        db_submission.submission_type = SubmissionType.REPO_URL
        db_submission.phase_id = 4
        db_submission.submitted_value = "https://github.com/testuser/webapp"
        db_submission.extracted_username = "testuser"
        db_submission.is_validated = True
        db_submission.validated_at = now
        db_submission.created_at = now

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
            patch(
                "services.submissions_service.validate_submission",
                return_value=validation_result,
            ),
            patch(
                "services.submissions_service.parse_github_url", return_value=parsed_url
            ),
            patch("services.submissions_service.SubmissionRepository") as MockRepo,
            patch("services.submissions_service.log_metric"),
            patch("services.submissions_service.invalidate_progress_cache"),
        ):
            repo_instance = AsyncMock()
            repo_instance.upsert.return_value = db_submission
            MockRepo.return_value = repo_instance

            result = await submit_validation(
                mock_db,
                user_id="user-1",
                requirement_id="deploy-webapp",
                submitted_value="https://github.com/testuser/webapp",
                github_username="testuser",
            )

        assert isinstance(result, SubmissionResult)
        assert result.is_valid is True
        assert result.submission.requirement_id == "deploy-webapp"

    @pytest.mark.asyncio
    async def test_logs_validated_metric_on_success(self, mock_db):
        """Logs 'submissions.validated' metric on successful validation."""
        now = datetime.now()

        requirement = MagicMock()
        requirement.submission_type = SubmissionType.DEPLOYED_APP
        requirement.phase_id = 4

        validation_result = MagicMock()
        validation_result.is_valid = True
        validation_result.message = "Validated"
        validation_result.username_match = None
        validation_result.repo_exists = None

        parsed_url = MagicMock()
        parsed_url.is_valid = False

        db_submission = MagicMock()
        db_submission.id = 1
        db_submission.requirement_id = "req-1"
        db_submission.submission_type = SubmissionType.DEPLOYED_APP
        db_submission.phase_id = 4
        db_submission.submitted_value = "https://app.azurewebsites.net"
        db_submission.extracted_username = None
        db_submission.is_validated = True
        db_submission.validated_at = now
        db_submission.created_at = now

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
            patch(
                "services.submissions_service.validate_submission",
                return_value=validation_result,
            ),
            patch(
                "services.submissions_service.parse_github_url", return_value=parsed_url
            ),
            patch("services.submissions_service.SubmissionRepository") as MockRepo,
            patch("services.submissions_service.log_metric") as mock_metric,
            patch("services.submissions_service.invalidate_progress_cache"),
        ):
            repo_instance = AsyncMock()
            repo_instance.upsert.return_value = db_submission
            MockRepo.return_value = repo_instance

            await submit_validation(
                mock_db,
                user_id="user-1",
                requirement_id="req-1",
                submitted_value="https://app.azurewebsites.net",
                github_username="testuser",
            )

        mock_metric.assert_called_once_with(
            "submissions.validated",
            1,
            {"phase": "phase4", "type": "deployed_app"},
        )

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self, mock_db):
        """Invalidates progress cache after successful validation."""
        now = datetime.now()

        requirement = MagicMock()
        requirement.submission_type = SubmissionType.DEPLOYED_APP
        requirement.phase_id = 4

        validation_result = MagicMock()
        validation_result.is_valid = True
        validation_result.message = "Validated"
        validation_result.username_match = None
        validation_result.repo_exists = None

        parsed_url = MagicMock()
        parsed_url.is_valid = False

        db_submission = MagicMock()
        db_submission.id = 1
        db_submission.requirement_id = "req-1"
        db_submission.submission_type = SubmissionType.DEPLOYED_APP
        db_submission.phase_id = 4
        db_submission.submitted_value = "https://app.azurewebsites.net"
        db_submission.extracted_username = None
        db_submission.is_validated = True
        db_submission.validated_at = now
        db_submission.created_at = now

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
            patch(
                "services.submissions_service.validate_submission",
                return_value=validation_result,
            ),
            patch(
                "services.submissions_service.parse_github_url", return_value=parsed_url
            ),
            patch("services.submissions_service.SubmissionRepository") as MockRepo,
            patch("services.submissions_service.log_metric"),
            patch(
                "services.submissions_service.invalidate_progress_cache"
            ) as mock_invalidate,
        ):
            repo_instance = AsyncMock()
            repo_instance.upsert.return_value = db_submission
            MockRepo.return_value = repo_instance

            await submit_validation(
                mock_db,
                user_id="user-1",
                requirement_id="req-1",
                submitted_value="https://app.azurewebsites.net",
                github_username="testuser",
            )

        mock_invalidate.assert_called_once_with("user-1")

    @pytest.mark.asyncio
    async def test_logs_failed_metric_on_failure(self, mock_db):
        """Logs 'submissions.failed' metric on failed validation."""
        now = datetime.now()

        requirement = MagicMock()
        requirement.submission_type = SubmissionType.DEPLOYED_APP
        requirement.phase_id = 4

        validation_result = MagicMock()
        validation_result.is_valid = False  # Failed validation
        validation_result.message = "App not accessible"
        validation_result.username_match = None
        validation_result.repo_exists = None

        parsed_url = MagicMock()
        parsed_url.is_valid = False

        db_submission = MagicMock()
        db_submission.id = 1
        db_submission.requirement_id = "req-1"
        db_submission.submission_type = SubmissionType.DEPLOYED_APP
        db_submission.phase_id = 4
        db_submission.submitted_value = "https://app.azurewebsites.net"
        db_submission.extracted_username = None
        db_submission.is_validated = False
        db_submission.validated_at = None
        db_submission.created_at = now

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
            patch(
                "services.submissions_service.validate_submission",
                return_value=validation_result,
            ),
            patch(
                "services.submissions_service.parse_github_url", return_value=parsed_url
            ),
            patch("services.submissions_service.SubmissionRepository") as MockRepo,
            patch("services.submissions_service.log_metric") as mock_metric,
            patch("services.submissions_service.invalidate_progress_cache"),
        ):
            repo_instance = AsyncMock()
            repo_instance.upsert.return_value = db_submission
            MockRepo.return_value = repo_instance

            await submit_validation(
                mock_db,
                user_id="user-1",
                requirement_id="req-1",
                submitted_value="https://app.azurewebsites.net",
                github_username="testuser",
            )

        mock_metric.assert_called_once_with(
            "submissions.failed",
            1,
            {"phase": "phase4", "type": "deployed_app"},
        )

    @pytest.mark.asyncio
    async def test_extracts_github_username_from_url(self, mock_db):
        """Extracts GitHub username from submitted URL."""
        now = datetime.now()

        requirement = MagicMock()
        requirement.submission_type = SubmissionType.REPO_URL
        requirement.phase_id = 4

        validation_result = MagicMock()
        validation_result.is_valid = True
        validation_result.message = "Validated"
        validation_result.username_match = True
        validation_result.repo_exists = True

        parsed_url = MagicMock()
        parsed_url.is_valid = True
        parsed_url.username = "extracted-user"

        db_submission = MagicMock()
        db_submission.id = 1
        db_submission.requirement_id = "req-1"
        db_submission.submission_type = SubmissionType.REPO_URL
        db_submission.phase_id = 4
        db_submission.submitted_value = "https://github.com/extracted-user/repo"
        db_submission.extracted_username = "extracted-user"
        db_submission.is_validated = True
        db_submission.validated_at = now
        db_submission.created_at = now

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
            patch(
                "services.submissions_service.validate_submission",
                return_value=validation_result,
            ),
            patch(
                "services.submissions_service.parse_github_url", return_value=parsed_url
            ),
            patch("services.submissions_service.SubmissionRepository") as MockRepo,
            patch("services.submissions_service.log_metric"),
            patch("services.submissions_service.invalidate_progress_cache"),
        ):
            repo_instance = AsyncMock()
            repo_instance.upsert.return_value = db_submission
            MockRepo.return_value = repo_instance

            await submit_validation(
                mock_db,
                user_id="user-1",
                requirement_id="req-1",
                submitted_value="https://github.com/extracted-user/repo",
                github_username="testuser",
            )

        # Verify upsert was called with extracted username
        call_kwargs = repo_instance.upsert.call_args.kwargs
        assert call_kwargs["extracted_username"] == "extracted-user"

    @pytest.mark.asyncio
    async def test_ctf_token_uses_github_username_as_extracted(self, mock_db):
        """CTF tokens use the linked GitHub username as extracted_username."""
        now = datetime.now()

        requirement = MagicMock()
        requirement.submission_type = SubmissionType.CTF_TOKEN
        requirement.phase_id = 2

        validation_result = MagicMock()
        validation_result.is_valid = True
        validation_result.message = "Token validated"
        validation_result.username_match = True
        validation_result.repo_exists = None

        db_submission = MagicMock()
        db_submission.id = 1
        db_submission.requirement_id = "ctf-1"
        db_submission.submission_type = SubmissionType.CTF_TOKEN
        db_submission.phase_id = 2
        db_submission.submitted_value = "token-secret"
        db_submission.extracted_username = "myuser"
        db_submission.is_validated = True
        db_submission.validated_at = now
        db_submission.created_at = now

        with (
            patch(
                "services.submissions_service.get_requirement_by_id",
                return_value=requirement,
            ),
            patch("services.submissions_service.add_custom_attribute"),
            patch(
                "services.submissions_service.validate_submission",
                return_value=validation_result,
            ),
            patch("services.submissions_service.parse_github_url") as mock_parse,
            patch("services.submissions_service.SubmissionRepository") as MockRepo,
            patch("services.submissions_service.log_metric"),
            patch("services.submissions_service.invalidate_progress_cache"),
        ):
            repo_instance = AsyncMock()
            repo_instance.upsert.return_value = db_submission
            MockRepo.return_value = repo_instance

            await submit_validation(
                mock_db,
                user_id="user-1",
                requirement_id="ctf-1",
                submitted_value="token-secret",
                github_username="myuser",
            )

        # parse_github_url should not be called for CTF tokens
        mock_parse.assert_not_called()

        # Should use github_username as extracted_username
        call_kwargs = repo_instance.upsert.call_args.kwargs
        assert call_kwargs["extracted_username"] == "myuser"
