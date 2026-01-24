"""Tests for the hands-on verification service module.

Tests validation functions for deployed apps, Journal API responses,
and the main submission routing logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from circuitbreaker import CircuitBreakerError

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult


class TestIsPublicIp:
    """Tests for _is_public_ip function."""

    def test_public_ipv4(self):
        """Public IPv4 addresses should return True."""
        from services.hands_on_verification_service import _is_public_ip

        assert _is_public_ip("8.8.8.8") is True
        assert _is_public_ip("1.1.1.1") is True

    def test_private_ipv4(self):
        """Private IPv4 addresses should return False."""
        from services.hands_on_verification_service import _is_public_ip

        assert _is_public_ip("192.168.1.1") is False
        assert _is_public_ip("10.0.0.1") is False
        assert _is_public_ip("172.16.0.1") is False

    def test_loopback_ipv4(self):
        """Loopback addresses should return False."""
        from services.hands_on_verification_service import _is_public_ip

        assert _is_public_ip("127.0.0.1") is False

    def test_link_local_ipv4(self):
        """Link-local addresses should return False."""
        from services.hands_on_verification_service import _is_public_ip

        assert _is_public_ip("169.254.1.1") is False

    def test_invalid_ip(self):
        """Invalid IP strings should return False."""
        from services.hands_on_verification_service import _is_public_ip

        assert _is_public_ip("not-an-ip") is False
        assert _is_public_ip("") is False


class TestHostResolvesToPublicIp:
    """Tests for _host_resolves_to_public_ip function."""

    @pytest.mark.asyncio
    async def test_direct_public_ip(self):
        """Direct public IP should return True."""
        from services.hands_on_verification_service import _host_resolves_to_public_ip

        result = await _host_resolves_to_public_ip("8.8.8.8")
        assert result is True

    @pytest.mark.asyncio
    async def test_direct_private_ip(self):
        """Direct private IP should return False."""
        from services.hands_on_verification_service import _host_resolves_to_public_ip

        result = await _host_resolves_to_public_ip("192.168.1.1")
        assert result is False

    @pytest.mark.asyncio
    async def test_hostname_resolves_to_public(self):
        """Hostname resolving to public IP should return True."""
        from services.hands_on_verification_service import _host_resolves_to_public_ip

        with patch("services.hands_on_verification_service.asyncio.to_thread") as mock:
            mock.return_value = ["8.8.8.8"]
            result = await _host_resolves_to_public_ip("example.com")
            assert result is True

    @pytest.mark.asyncio
    async def test_hostname_resolves_to_private(self):
        """Hostname resolving to private IP should return False."""
        from services.hands_on_verification_service import _host_resolves_to_public_ip

        with patch("services.hands_on_verification_service.asyncio.to_thread") as mock:
            mock.return_value = ["192.168.1.1"]
            result = await _host_resolves_to_public_ip("internal.local")
            assert result is False

    @pytest.mark.asyncio
    async def test_hostname_resolution_fails(self):
        """Failed DNS resolution should return False."""
        import socket

        from services.hands_on_verification_service import _host_resolves_to_public_ip

        with patch("services.hands_on_verification_service.asyncio.to_thread") as mock:
            mock.side_effect = socket.gaierror()
            result = await _host_resolves_to_public_ip("nonexistent.invalid")
            assert result is False


class TestValidatePublicHttpsUrl:
    """Tests for _validate_public_https_url function."""

    @pytest.mark.asyncio
    async def test_valid_https_url(self):
        """Valid HTTPS URL should be accepted."""
        from services.hands_on_verification_service import _validate_public_https_url

        with patch(
            "services.hands_on_verification_service._host_resolves_to_public_ip"
        ) as mock:
            mock.return_value = True
            result = await _validate_public_https_url("https://example.com/path")
            assert "https://example.com/path" in result

    @pytest.mark.asyncio
    async def test_http_url_rejected(self):
        """HTTP URL should be rejected."""
        from services.hands_on_verification_service import _validate_public_https_url

        with pytest.raises(ValueError, match="must use https"):
            await _validate_public_https_url("http://example.com")

    @pytest.mark.asyncio
    async def test_url_with_credentials_rejected(self):
        """URL with embedded credentials should be rejected."""
        from services.hands_on_verification_service import _validate_public_https_url

        with pytest.raises(ValueError, match="must not include credentials"):
            await _validate_public_https_url("https://user:pass@example.com")

    @pytest.mark.asyncio
    async def test_private_host_rejected(self):
        """URL resolving to private IP should be rejected."""
        from services.hands_on_verification_service import _validate_public_https_url

        with patch(
            "services.hands_on_verification_service._host_resolves_to_public_ip"
        ) as mock:
            mock.return_value = False
            with pytest.raises(ValueError, match="not publicly routable"):
                await _validate_public_https_url("https://internal.local")


class TestValidateJournalApiResponse:
    """Tests for validate_journal_api_response function."""

    def test_empty_response(self):
        """Empty response should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        result = validate_journal_api_response("")
        assert result.is_valid is False
        assert "Please paste" in result.message

    def test_invalid_json(self):
        """Invalid JSON should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        result = validate_journal_api_response("not json")
        assert result.is_valid is False
        assert "Invalid JSON" in result.message

    def test_empty_array(self):
        """Empty array should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        result = validate_journal_api_response("[]")
        assert result.is_valid is False
        assert "No entries found" in result.message

    def test_valid_array_response(self):
        """Valid array with entries should be valid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """[{
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "work": "Did some work",
            "struggle": "Had struggles",
            "intention": "Tomorrow's plan",
            "created_at": "2024-01-15T10:30:00Z"
        }]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "1 entry" in result.message

    def test_valid_wrapped_response(self):
        """Valid wrapped response with 'entries' key should be valid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """{
            "entries": [{
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "work": "Work done",
                "struggle": "Struggles",
                "intention": "Plans",
                "created_at": "2024-01-15T10:30:00+00:00"
            }],
            "count": 1
        }"""
        result = validate_journal_api_response(response)
        assert result.is_valid is True

    def test_missing_required_fields(self):
        """Entries missing required fields should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """[{
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "work": "Work"
        }]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "missing required fields" in result.message

    def test_invalid_uuid_format(self):
        """Entries with invalid UUID should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """[{
            "id": "not-a-uuid",
            "work": "Work",
            "struggle": "Struggle",
            "intention": "Intention",
            "created_at": "2024-01-15T10:30:00Z"
        }]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "invalid ID format" in result.message

    def test_empty_text_fields(self):
        """Entries with empty text fields should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """[{
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "work": "",
            "struggle": "Struggle",
            "intention": "Intention",
            "created_at": "2024-01-15T10:30:00Z"
        }]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "empty or invalid 'work'" in result.message

    def test_invalid_created_at_format(self):
        """Entries with invalid datetime should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """[{
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "work": "Work",
            "struggle": "Struggle",
            "intention": "Intention",
            "created_at": "not-a-date"
        }]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "invalid created_at" in result.message

    def test_multiple_entries(self):
        """Multiple valid entries should show count."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = """[
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "work": "Work 1",
                "struggle": "Struggle 1",
                "intention": "Intention 1",
                "created_at": "2024-01-15T10:30:00Z"
            },
            {
                "id": "223e4567-e89b-12d3-a456-426614174001",
                "work": "Work 2",
                "struggle": "Struggle 2",
                "intention": "Intention 2",
                "created_at": "2024-01-16T10:30:00Z"
            }
        ]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "2 entries" in result.message

    def test_non_dict_entry(self):
        """Entry that is not a dict should be invalid."""
        from services.hands_on_verification_service import validate_journal_api_response

        response = '["not an object"]'
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "not a valid object" in result.message

    def test_response_not_array_or_object(self):
        """Response that is neither array nor object with entries should fail."""
        from services.hands_on_verification_service import validate_journal_api_response

        result = validate_journal_api_response('"just a string"')
        assert result.is_valid is False
        assert "should be a JSON array" in result.message


class TestValidateDeployedApp:
    """Tests for validate_deployed_app function."""

    @pytest.mark.asyncio
    async def test_successful_200_response(self):
        """App returning 200 should be valid."""
        from services.hands_on_verification_service import validate_deployed_app

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "OK"

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.return_value = "https://app.example.com"

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.return_value = mock_response
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app("https://app.example.com")
                assert result.is_valid is True
                assert "is live" in result.message

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Timeout should return descriptive error."""
        from services.hands_on_verification_service import validate_deployed_app

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.return_value = "https://slow-app.example.com"

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.side_effect = httpx.TimeoutException("Timeout")
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app("https://slow-app.example.com")
                assert result.is_valid is False
                assert "timed out" in result.message

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Connection error should return descriptive error."""
        from services.hands_on_verification_service import validate_deployed_app

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.return_value = "https://offline.example.com"

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.side_effect = httpx.ConnectError("Connection failed")
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app("https://offline.example.com")
                assert result.is_valid is False
                assert "Could not connect" in result.message

    @pytest.mark.asyncio
    async def test_404_error(self):
        """404 should return endpoint not found error."""
        from services.hands_on_verification_service import validate_deployed_app

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.return_value = "https://app.example.com/missing"

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.return_value = mock_response
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app(
                    "https://app.example.com", "/missing"
                )
                assert result.is_valid is False
                assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_401_403_auth_error(self):
        """401/403 should indicate auth required."""
        from services.hands_on_verification_service import validate_deployed_app

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.return_value = "https://app.example.com/protected"

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.return_value = mock_response
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app(
                    "https://app.example.com", "/protected"
                )
                assert result.is_valid is False
                assert "authentication" in result.message

    @pytest.mark.asyncio
    async def test_redirect_handling(self):
        """Redirects should be followed up to limit."""
        from services.hands_on_verification_service import validate_deployed_app

        redirect_response = MagicMock()
        redirect_response.status_code = 301
        redirect_response.headers = {"location": "https://app.example.com/final"}

        final_response = MagicMock()
        final_response.status_code = 200
        final_response.headers = {}
        final_response.text = "OK"

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.side_effect = [
                "https://app.example.com",
                "https://app.example.com/final",
            ]

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.side_effect = [redirect_response, final_response]
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app("https://app.example.com")
                assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_invalid_url_rejected(self):
        """Invalid URL should be rejected."""
        from services.hands_on_verification_service import validate_deployed_app

        with patch(
            "services.hands_on_verification_service._validate_public_https_url"
        ) as mock_validate:
            mock_validate.side_effect = ValueError("URL must use https")

            with patch(
                "services.hands_on_verification_service.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await validate_deployed_app("http://insecure.example.com")
                assert result.is_valid is False
                assert "https" in result.message


class TestValidateCtfTokenSubmission:
    """Tests for validate_ctf_token_submission function."""

    def test_valid_ctf_token(self):
        """Valid CTF token should be accepted."""
        from services.hands_on_verification_service import validate_ctf_token_submission

        with patch(
            "services.hands_on_verification_service.verify_ctf_token"
        ) as mock_verify:
            mock_verify.return_value = ValidationResult(
                is_valid=True, message="CTF completed!"
            )

            result = validate_ctf_token_submission("valid-token", "testuser")
            assert result.is_valid is True
            assert result.username_match is True

    def test_invalid_ctf_token(self):
        """Invalid CTF token should be rejected."""
        from services.hands_on_verification_service import validate_ctf_token_submission

        with patch(
            "services.hands_on_verification_service.verify_ctf_token"
        ) as mock_verify:
            mock_verify.return_value = ValidationResult(
                is_valid=False, message="Invalid token"
            )

            result = validate_ctf_token_submission("bad-token", "testuser")
            assert result.is_valid is False
            assert result.username_match is False


class TestValidateSubmission:
    """Tests for validate_submission routing function."""

    @pytest.mark.asyncio
    async def test_profile_readme_routing(self):
        """PROFILE_README should route to validate_profile_readme."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.PROFILE_README,
        )

        with patch(
            "services.hands_on_verification_service.validate_profile_readme"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(
                requirement, "https://github.com/user/user", "user"
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_profile_readme_requires_username(self):
        """PROFILE_README without username should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.PROFILE_README,
        )

        result = await validate_submission(
            requirement, "https://github.com/user/user", None
        )
        assert result.is_valid is False
        assert "username is required" in result.message

    @pytest.mark.asyncio
    async def test_deployed_app_routing(self):
        """DEPLOYED_APP should route to validate_deployed_app."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.DEPLOYED_APP,
            expected_endpoint="/entries",
            validate_response_body=False,
        )

        with patch(
            "services.hands_on_verification_service.validate_deployed_app"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(requirement, "https://app.example.com", None)
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_deployed_app_circuit_breaker(self):
        """DEPLOYED_APP should handle circuit breaker error."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.DEPLOYED_APP,
        )

        with patch(
            "services.hands_on_verification_service.validate_deployed_app"
        ) as mock:
            mock.side_effect = CircuitBreakerError(MagicMock())

            result = await validate_submission(
                requirement, "https://app.example.com", None
            )
            assert result.is_valid is False
            assert "temporarily unavailable" in result.message

    @pytest.mark.asyncio
    async def test_ctf_token_routing(self):
        """CTF_TOKEN should route to validate_ctf_token_submission."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.CTF_TOKEN,
        )

        with patch(
            "services.hands_on_verification_service.validate_ctf_token_submission"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(requirement, "token123", "user")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_ctf_token_requires_username(self):
        """CTF_TOKEN without username should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.CTF_TOKEN,
        )

        result = await validate_submission(requirement, "token123", None)
        assert result.is_valid is False
        assert "username is required" in result.message

    @pytest.mark.asyncio
    async def test_github_profile_routing(self):
        """GITHUB_PROFILE should route to validate_github_profile."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.GITHUB_PROFILE,
        )

        with patch(
            "services.hands_on_verification_service.validate_github_profile"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(requirement, "https://github.com/user", "user")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_url_routing(self):
        """REPO_URL should route to validate_repo_url."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.REPO_URL,
        )

        with patch("services.hands_on_verification_service.validate_repo_url") as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(
                requirement, "https://github.com/user/repo", "user"
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_journal_api_response_routing(self):
        """JOURNAL_API_RESPONSE should route to validate_journal_api_response."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.JOURNAL_API_RESPONSE,
        )

        with patch(
            "services.hands_on_verification_service.validate_journal_api_response"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(requirement, '[{"id": "123"}]', None)
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_fork_routing(self):
        """REPO_FORK should route to validate_repo_fork."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.REPO_FORK,
            required_repo="original/repo",
        )

        with patch("services.hands_on_verification_service.validate_repo_fork") as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(
                requirement, "https://github.com/user/repo", "user"
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_fork_missing_required_repo(self):
        """REPO_FORK without required_repo should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.REPO_FORK,
            required_repo=None,
        )

        result = await validate_submission(
            requirement, "https://github.com/user/repo", "user"
        )
        assert result.is_valid is False
        assert "missing required_repo" in result.message

    @pytest.mark.asyncio
    async def test_workflow_run_routing(self):
        """WORKFLOW_RUN should route to validate_workflow_run."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.WORKFLOW_RUN,
        )

        with patch(
            "services.hands_on_verification_service.validate_workflow_run"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(
                requirement, "https://github.com/user/repo", "user"
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_with_files_routing(self):
        """REPO_WITH_FILES should route to validate_repo_has_files."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.REPO_WITH_FILES,
            required_file_patterns=["Dockerfile"],
            file_description="Docker files",
        )

        with patch(
            "services.hands_on_verification_service.validate_repo_has_files"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(
                requirement, "https://github.com/user/repo", "user"
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_with_files_missing_patterns(self):
        """REPO_WITH_FILES without patterns should fail."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.REPO_WITH_FILES,
            required_file_patterns=None,
        )

        result = await validate_submission(
            requirement, "https://github.com/user/repo", "user"
        )
        assert result.is_valid is False
        assert "missing required_file_patterns" in result.message

    @pytest.mark.asyncio
    async def test_container_image_routing(self):
        """CONTAINER_IMAGE should route to validate_container_image."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.CONTAINER_IMAGE,
        )

        with patch(
            "services.hands_on_verification_service.validate_container_image"
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="OK")

            await validate_submission(requirement, "docker.io/user/image", "user")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_challenge_not_implemented(self):
        """API_CHALLENGE should return not implemented."""
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="test-req",
            phase_id=1,
            name="Test",
            description="Test",
            submission_type=SubmissionType.API_CHALLENGE,
        )

        result = await validate_submission(requirement, "challenge-response", None)
        assert result.is_valid is False
        assert "not yet implemented" in result.message


class TestValidateDeployedJournalResponse:
    """Tests for _validate_deployed_journal_response function."""

    def test_valid_deployed_response(self):
        """Valid deployed journal response should pass."""
        from services.hands_on_verification_service import (
            _validate_deployed_journal_response,
        )

        response = """[{
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "work": "Work",
            "struggle": "Struggle",
            "intention": "Intention",
            "created_at": "2024-01-15T10:30:00Z"
        }]"""

        result = _validate_deployed_journal_response(
            response, "https://app.example.com"
        )
        assert result.is_valid is True
        assert "deployed" in result.message.lower()

    def test_invalid_json_deployed(self):
        """Invalid JSON from deployed API should fail with specific message."""
        from services.hands_on_verification_service import (
            _validate_deployed_journal_response,
        )

        result = _validate_deployed_journal_response(
            "not json", "https://app.example.com"
        )
        assert result.is_valid is False
        assert "not valid JSON" in result.message

    def test_no_entries_deployed(self):
        """Empty entries from deployed API should have deployment-specific message."""
        from services.hands_on_verification_service import (
            _validate_deployed_journal_response,
        )

        result = _validate_deployed_journal_response("[]", "https://app.example.com")
        assert result.is_valid is False
        assert "deployed" in result.message.lower()

    def test_missing_fields_deployed(self):
        """Missing fields from deployed API should have deployment-specific message."""
        from services.hands_on_verification_service import (
            _validate_deployed_journal_response,
        )

        response = """[{
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "work": "Work"
        }]"""

        result = _validate_deployed_journal_response(
            response, "https://app.example.com"
        )
        assert result.is_valid is False
        assert "missing" in result.message.lower()
