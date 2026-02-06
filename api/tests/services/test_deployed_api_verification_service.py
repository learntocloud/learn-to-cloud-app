"""Unit tests for deployed_api_verification_service.

Tests the live API health check and JSON response validation:
- URL normalization and validation
- HTTP request handling (success, errors, timeouts)
- JSON response parsing and entry validation
- Circuit breaker behavior
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from circuitbreaker import CircuitBreakerError

from services.deployed_api_verification_service import (
    DeployedApiServerError,
    _normalize_base_url,
    _validate_entries_json,
    _validate_entry,
    validate_deployed_api,
)


class TestNormalizeBaseUrl:
    """Tests for URL normalization."""

    def test_strips_trailing_slash(self):
        """Trailing slashes should be removed."""
        assert (
            _normalize_base_url("https://api.example.com/") == "https://api.example.com"
        )

    def test_strips_entries_suffix(self):
        """If user includes /entries, it should be stripped."""
        assert (
            _normalize_base_url("https://api.example.com/entries")
            == "https://api.example.com"
        )
        assert (
            _normalize_base_url("https://api.example.com/entries/")
            == "https://api.example.com"
        )

    def test_strips_whitespace(self):
        """Leading/trailing whitespace should be removed."""
        assert (
            _normalize_base_url("  https://api.example.com  ")
            == "https://api.example.com"
        )

    def test_preserves_path(self):
        """Path segments other than /entries should be preserved."""
        assert (
            _normalize_base_url("https://api.example.com/v1")
            == "https://api.example.com/v1"
        )


class TestValidateEntry:
    """Tests for individual entry validation."""

    def _valid_entry(self) -> dict:
        """Create a valid journal entry for testing."""
        return {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

    def test_valid_entry_passes(self):
        """A valid entry should pass validation."""
        is_valid, error = _validate_entry(self._valid_entry(), 0)
        assert is_valid is True
        assert error is None

    def test_missing_field_fails(self):
        """Entry missing required fields should fail."""
        entry = self._valid_entry()
        del entry["work"]

        is_valid, error = _validate_entry(entry, 0)
        assert is_valid is False
        assert error is not None
        assert "missing fields" in error.lower()
        assert "work" in error

    def test_invalid_uuid_fails(self):
        """Entry with invalid UUID should fail."""
        entry = self._valid_entry()
        entry["id"] = "not-a-uuid"

        is_valid, error = _validate_entry(entry, 0)
        assert is_valid is False
        assert error is not None
        assert "invalid id" in error.lower()

    def test_empty_string_field_fails(self):
        """Entry with empty string field should fail."""
        entry = self._valid_entry()
        entry["work"] = "   "

        is_valid, error = _validate_entry(entry, 0)
        assert is_valid is False
        assert error is not None
        assert "cannot be empty" in error.lower()

    def test_invalid_datetime_fails(self):
        """Entry with invalid datetime should fail."""
        entry = self._valid_entry()
        entry["created_at"] = "not-a-date"

        is_valid, error = _validate_entry(entry, 0)
        assert is_valid is False
        assert error is not None
        assert "invalid created_at" in error.lower()

    def test_optional_updated_at_validated(self):
        """If updated_at is present, it must be valid."""
        entry = self._valid_entry()
        entry["updated_at"] = "invalid"

        is_valid, error = _validate_entry(entry, 0)
        assert is_valid is False
        assert error is not None
        assert "invalid updated_at" in error.lower()


class TestValidateEntriesJson:
    """Tests for entries array validation."""

    def _valid_entry(self) -> dict:
        """Create a valid journal entry for testing."""
        return {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

    def test_valid_array_passes(self):
        """Valid array with entries should pass."""
        result = _validate_entries_json([self._valid_entry()])
        assert result.is_valid is True
        assert "1 valid entry" in result.message

    def test_multiple_entries_passes(self):
        """Multiple valid entries should pass."""
        entries = [self._valid_entry(), self._valid_entry()]
        entries[1]["id"] = "87654321-4321-4567-89ab-987654321abc"

        result = _validate_entries_json(entries)
        assert result.is_valid is True
        assert "2 valid entries" in result.message

    def test_empty_array_fails(self):
        """Empty array should fail."""
        result = _validate_entries_json([])
        assert result.is_valid is False
        assert "no entries" in result.message.lower()

    def test_non_object_entry_fails(self):
        """Non-object entries should fail."""
        result = _validate_entries_json(["not an object"])
        assert result.is_valid is False
        assert "not a valid object" in result.message.lower()


@pytest.mark.unit
class TestValidateDeployedApi:
    """Tests for the main validation function."""

    @pytest.mark.asyncio
    async def test_empty_url_fails(self):
        """Empty URL should fail."""
        result = await validate_deployed_api("")
        assert result.is_valid is False
        assert "submit your deployed api" in result.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_url_fails(self):
        """Invalid URL format should fail."""
        result = await validate_deployed_api("not-a-url")
        assert result.is_valid is False
        assert "valid HTTP(S) URL" in result.message

    @pytest.mark.asyncio
    async def test_successful_verification(self):
        """Successful API call with valid response should pass."""
        valid_entry = {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [valid_entry]

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            mock_fetch.assert_called_once_with("https://api.example.com/entries")
            assert result.is_valid is True
            assert "verified" in result.message.lower()

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Timeout should return appropriate error."""
        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.side_effect = httpx.TimeoutException("Request timed out")

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "timed out" in result.message.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Connection error should return appropriate message."""
        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.side_effect = httpx.ConnectError("Connection refused")

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "could not connect" in result.message.lower()

    @pytest.mark.asyncio
    async def test_server_error(self):
        """5xx errors should return appropriate message."""
        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.side_effect = DeployedApiServerError("Server returned 500")

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "server error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self):
        """Circuit breaker open should return retry message."""
        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.side_effect = CircuitBreakerError(MagicMock())

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "try again" in result.message.lower()

    @pytest.mark.asyncio
    async def test_404_not_found(self):
        """404 response should indicate endpoint doesn't exist."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "404" in result.message
            assert "endpoint exists" in result.message.lower()

    @pytest.mark.asyncio
    async def test_401_unauthorized(self):
        """401 response should indicate endpoint is not public."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "publicly accessible" in result.message.lower()

    @pytest.mark.asyncio
    async def test_403_forbidden(self):
        """403 response should indicate endpoint is not public."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "publicly accessible" in result.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        """Non-JSON response should fail."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "valid JSON" in result.message

    @pytest.mark.asyncio
    async def test_non_array_response(self):
        """Non-array JSON response should fail."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "not an array"}

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "array" in result.message.lower()

    @pytest.mark.asyncio
    async def test_url_with_entries_suffix_normalized(self):
        """URL ending in /entries should be normalized."""
        valid_entry = {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [valid_entry]

        with patch(
            "services.deployed_api_verification_service._fetch_entries_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            # User submits with /entries already
            result = await validate_deployed_api("https://api.example.com/entries")

            # Should still call /entries (not /entries/entries)
            mock_fetch.assert_called_once_with("https://api.example.com/entries")
            assert result.is_valid is True


@pytest.mark.unit
class TestValidateSubmissionIntegration:
    """Tests that DEPLOYED_API routes to the verification service."""

    @pytest.mark.asyncio
    async def test_deployed_api_routes_to_verification(self):
        """DEPLOYED_API should route to validate_deployed_api."""
        from models import SubmissionType
        from schemas import HandsOnRequirement, ValidationResult
        from services.hands_on_verification_service import validate_submission

        requirement = HandsOnRequirement(
            id="deployed-journal-api",
            phase_id=4,
            submission_type=SubmissionType.DEPLOYED_API,
            name="Deployed API",
            description="Test",
        )

        with patch(
            "services.deployed_api_verification_service.validate_deployed_api",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = ValidationResult(is_valid=True, message="API verified!")

            result = await validate_submission(
                requirement=requirement,
                submitted_value="https://api.example.com",
                expected_username=None,  # Not required for deployed API
            )

            mock.assert_called_once_with("https://api.example.com")
            assert result.is_valid is True
