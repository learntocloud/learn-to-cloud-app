"""Unit tests for deployed_api_verification_service.

Tests the challenge-response API ownership verification:
- URL normalization and validation
- Challenge nonce generation
- POST/GET/DELETE flow for ownership proof
- HTTP request handling (success, errors, timeouts)
- JSON response parsing and entry validation
- Transport retries and safe error diagnostics
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import deployed_api
from learn_to_cloud_shared.verification.deployed_api import (
    DeployedApiServerError,
    _check_response_ip,
    _extract_entries_list,
    _generate_challenge_nonce,
    _is_private_ip,
    _normalize_base_url,
    _SsrfError,
    _validate_analysis_json,
    _validate_entry,
    _validate_url_target,
    _verify_analysis,
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
        is_valid, error = _validate_entry(self._valid_entry())
        assert is_valid is True
        assert error is None

    def test_missing_field_fails(self):
        """Entry missing required fields should fail."""
        entry = self._valid_entry()
        del entry["work"]

        is_valid, error = _validate_entry(entry)
        assert is_valid is False
        assert error is not None
        assert "missing fields" in error.lower()
        assert "work" in error

    def test_invalid_uuid_fails(self):
        """Entry with invalid UUID should fail."""
        entry = self._valid_entry()
        entry["id"] = "not-a-uuid"

        is_valid, error = _validate_entry(entry)
        assert is_valid is False
        assert error is not None
        assert "invalid id" in error.lower()

    def test_empty_string_field_fails(self):
        """Entry with empty string field should fail."""
        entry = self._valid_entry()
        entry["work"] = "   "

        is_valid, error = _validate_entry(entry)
        assert is_valid is False
        assert error is not None
        assert "cannot be empty" in error.lower()

    def test_invalid_datetime_fails(self):
        """Entry with invalid datetime should fail."""
        entry = self._valid_entry()
        entry["created_at"] = "not-a-date"

        is_valid, error = _validate_entry(entry)
        assert is_valid is False
        assert error is not None
        assert "invalid created_at" in error.lower()

    def test_optional_updated_at_validated(self):
        """If updated_at is present, it must be valid."""
        entry = self._valid_entry()
        entry["updated_at"] = "invalid"

        is_valid, error = _validate_entry(entry)
        assert is_valid is False
        assert error is not None
        assert "invalid updated_at" in error.lower()


class TestValidateAnalysisJson:
    """Tests for live AI analysis response validation."""

    def _valid_analysis(self) -> dict:
        return {
            "entry_id": "challenge-id",
            "sentiment": "neutral",
            "summary": "The learner made progress and identified a next step.",
            "topics": ["FastAPI", "cloud"],
        }

    def test_valid_analysis_passes(self):
        result = _validate_analysis_json(self._valid_analysis(), "challenge-id")
        assert result.is_valid is True

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("entry_id", "different-id", "entry_id"),
            ("sentiment", "mixed", "sentiment"),
            ("summary", " ", "summary"),
            ("topics", [], "topics"),
            ("topics", ["cloud", ""], "topics"),
        ],
    )
    def test_invalid_analysis_fails(self, field, value, message):
        analysis = self._valid_analysis()
        analysis[field] = value

        result = _validate_analysis_json(analysis, "challenge-id")

        assert result.is_valid is False
        assert message in result.message


@pytest.mark.unit
class TestVerifyAnalysis:
    """Tests for the deployed live AI request."""

    @pytest.mark.asyncio
    async def test_valid_response_passes(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {
            "entry_id": "challenge-id",
            "sentiment": "positive",
            "summary": "The learner completed the deployment.",
            "topics": ["deployment"],
        }

        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_once",
            autospec=True,
            return_value=response,
        ) as mock_fetch:
            result = await _verify_analysis(
                "https://api.example.com",
                "challenge-id",
            )

        assert result.is_valid is True
        mock_fetch.assert_awaited_once_with(
            "https://api.example.com/entries/challenge-id/analyze",
            method="POST",
            timeout=30.0,
        )

    @pytest.mark.asyncio
    async def test_timeout_fails(self):
        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_once",
            autospec=True,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            result = await _verify_analysis(
                "https://api.example.com",
                "challenge-id",
            )

        assert result.is_valid is False
        assert "timed out" in result.message.lower()


class TestExtractEntriesList:
    """Tests for _extract_entries_list helper."""

    def test_raw_array_rejected(self):
        """Raw array is not the journal-starter format and should return None."""
        data = [{"id": "1"}]
        assert _extract_entries_list(data) is None

    def test_wrapped_object(self):
        """Object with 'entries' key should extract the list."""
        entries = [{"id": "1"}]
        data = {"entries": entries, "count": 1}
        assert _extract_entries_list(data) == entries

    def test_unrecognised_format(self):
        """Unrecognised format should return None."""
        assert _extract_entries_list({"error": "bad"}) is None
        assert _extract_entries_list("string") is None

    def test_empty_entries_list(self):
        """Empty entries list should still be returned."""
        assert _extract_entries_list({"entries": [], "count": 0}) == []


class TestGenerateChallengeNonce:
    """Tests for challenge nonce generation."""

    def test_nonce_has_prefix(self):
        """Generated nonce should start with ltc-verify-."""
        nonce = _generate_challenge_nonce()
        assert nonce.startswith("ltc-verify-")

    def test_nonces_are_unique(self):
        """Each call should produce a different nonce."""
        nonces = {_generate_challenge_nonce() for _ in range(10)}
        assert len(nonces) == 10


@pytest.mark.unit
@patch(
    "learn_to_cloud_shared.verification.deployed_api._validate_url_target",
    new_callable=AsyncMock,
    return_value=None,
)
class TestValidateDeployedApi:
    """Tests for the challenge-response validation function."""

    @pytest.fixture(autouse=True)
    def _stub_live_analysis(self, monkeypatch):
        async def valid_analysis(_base_url: str, entry_id: str):
            return _validate_analysis_json(
                {
                    "entry_id": entry_id,
                    "sentiment": "neutral",
                    "summary": "The deployed AI endpoint returned a valid result.",
                    "topics": ["verification"],
                },
                entry_id,
            )

        monkeypatch.setattr(
            "learn_to_cloud_shared.verification.deployed_api._verify_analysis",
            valid_analysis,
        )

    @pytest.mark.asyncio
    async def test_empty_url_fails(self, _mock_ssrf):
        """Empty URL should fail."""
        result = await validate_deployed_api("")
        assert result.is_valid is False
        assert "submit your deployed api" in result.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_url_fails(self, _mock_ssrf):
        """Invalid URL format should fail."""
        result = await validate_deployed_api("not-a-url")
        assert result.is_valid is False
        assert "valid HTTP(S) URL" in result.message

    @pytest.mark.asyncio
    async def test_successful_challenge_response(self, _mock_ssrf):
        """Full POST-GET-DELETE flow should verify ownership."""
        valid_entry = {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

        # Track calls to distinguish POST vs GET
        call_log = []

        async def mock_fetch(url, *, method="GET", json_body=None):
            call_log.append(method)
            resp = MagicMock(spec=httpx.Response)

            if method == "POST":
                assert json_body is not None
                resp.status_code = 200
                nonce = json_body["work"]
                resp.json.return_value = {
                    "detail": "Entry created successfully",
                    "entry": {
                        "id": "87654321-4321-4567-89ab-987654321abc",
                        "work": nonce,
                        "struggle": json_body["struggle"],
                        "intention": json_body["intention"],
                        "created_at": "2026-01-01T00:00:00Z",
                    },
                }
                return resp

            if method == "GET":
                # Return the valid entry + challenge entry
                nonce_entry = {
                    "id": "87654321-4321-4567-89ab-987654321abc",
                    "work": call_log_nonce,
                    "struggle": "LTC verification challenge",
                    "intention": "Proving API ownership",
                    "created_at": "2026-01-01T00:00:00Z",
                }
                all_entries = [valid_entry, nonce_entry]
                resp.status_code = 200
                resp.json.return_value = {
                    "entries": all_entries,
                    "count": len(all_entries),
                }
                return resp

            return resp

        # We need to capture the nonce from the POST call
        call_log_nonce = None
        original_mock_fetch = mock_fetch

        async def capturing_mock_fetch(url, *, method="GET", json_body=None):
            nonlocal call_log_nonce
            if method == "POST" and json_body:
                call_log_nonce = json_body["work"]
            return await original_mock_fetch(url, method=method, json_body=json_body)

        with (
            patch(
                "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
                autospec=True,
                side_effect=capturing_mock_fetch,
            ),
            patch(
                "learn_to_cloud_shared.verification.deployed_api._cleanup_challenge_entry",
                autospec=True,
            ) as mock_cleanup,
        ):
            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is True
            assert "ownership confirmed" in result.message.lower()
            assert "valid entry" not in result.message
            mock_cleanup.assert_called_once_with(
                "https://api.example.com/entries",
                "87654321-4321-4567-89ab-987654321abc",
            )

    @pytest.mark.asyncio
    async def test_post_timeout_error(self, _mock_ssrf):
        """Timeout on POST should return appropriate error."""
        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
            autospec=True,
        ) as mock_fetch:
            mock_fetch.side_effect = httpx.TimeoutException("Request timed out")

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "timed out" in result.message.lower()

    @pytest.mark.asyncio
    async def test_post_connection_error(self, _mock_ssrf):
        """Connection error on POST should return appropriate message."""
        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
            autospec=True,
        ) as mock_fetch:
            mock_fetch.side_effect = httpx.ConnectError("Connection refused")

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "could not connect" in result.message.lower()

    @pytest.mark.asyncio
    async def test_post_server_error(self, _mock_ssrf):
        """5xx errors on POST should return appropriate message."""
        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
            autospec=True,
        ) as mock_fetch:
            mock_fetch.side_effect = DeployedApiServerError(
                "Server returned 500", status_code=500
            )

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "server error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_transient_failure(self, _mock_ssrf):
        """Transient connection failure should return retry message."""
        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
            autospec=True,
        ) as mock_fetch:
            mock_fetch.side_effect = httpx.ConnectError("connection refused")

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert (
                "connect" in result.message.lower() or "error" in result.message.lower()
            )

    @pytest.mark.asyncio
    async def test_post_404_not_found(self, _mock_ssrf):
        """POST 404 should indicate endpoint doesn't exist."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404

        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
            autospec=True,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "404" in result.message

    @pytest.mark.asyncio
    async def test_post_422_validation_error(self, _mock_ssrf):
        """POST 422 should indicate validation error."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 422

        with patch(
            "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
            autospec=True,
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await validate_deployed_api("https://api.example.com")

        assert result.verification_completed
        assert result.is_valid is False
        assert result.message == (
            "POST /entries returned 422 (validation error). "
            "Ensure POST /entries accepts {work, struggle, intention}."
        )
        mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nonce_not_found_in_get(self, _mock_ssrf):
        """If nonce is not in GET response, ownership verification fails."""
        post_response = MagicMock(spec=httpx.Response)
        post_response.status_code = 200
        post_response.json.return_value = {
            "entry": {"id": "challenge-id", "work": "ltc-verify-abc"}
        }

        get_response = MagicMock(spec=httpx.Response)
        get_response.status_code = 200
        # Return entries that don't contain the nonce (wrapped format)
        get_response.json.return_value = {
            "entries": [
                {
                    "id": "12345678-1234-4567-89ab-123456789abc",
                    "work": "Some real work",
                    "struggle": "stuff",
                    "intention": "things",
                    "created_at": "2025-01-01T00:00:00Z",
                }
            ],
            "count": 1,
        }

        call_count = 0

        async def mock_fetch(url, *, method="GET", json_body=None):
            nonlocal call_count
            call_count += 1
            if method == "POST":
                return post_response
            return get_response

        with (
            patch(
                "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
                autospec=True,
                side_effect=mock_fetch,
            ),
            patch(
                "learn_to_cloud_shared.verification.deployed_api._cleanup_challenge_entry",
                autospec=True,
            ),
        ):
            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "ownership verification failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_get_returns_invalid_json(self, _mock_ssrf):
        """Non-JSON GET response should fail after POST succeeds."""
        post_response = MagicMock(spec=httpx.Response)
        post_response.status_code = 200
        post_response.json.return_value = {"entry": {"id": "cid"}}

        get_response = MagicMock(spec=httpx.Response)
        get_response.status_code = 200
        get_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        call_count = 0

        async def mock_fetch(url, *, method="GET", json_body=None):
            nonlocal call_count
            call_count += 1
            if method == "POST":
                return post_response
            return get_response

        with (
            patch(
                "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
                autospec=True,
                side_effect=mock_fetch,
            ),
            patch(
                "learn_to_cloud_shared.verification.deployed_api._cleanup_challenge_entry",
                autospec=True,
            ),
        ):
            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is False
            assert "valid JSON" in result.message

    @pytest.mark.asyncio
    async def test_wrapped_response_format(self, _mock_ssrf):
        """API returning {"entries": [...], "count": N} should also work."""
        valid_entry = {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

        captured_nonce = None

        async def mock_fetch(url, *, method="GET", json_body=None):
            nonlocal captured_nonce
            resp = MagicMock(spec=httpx.Response)

            if method == "POST":
                assert json_body is not None
                captured_nonce = json_body["work"]
                resp.status_code = 200
                resp.json.return_value = {
                    "entry": {
                        "id": "87654321-4321-4567-89ab-987654321abc",
                        "work": captured_nonce,
                    }
                }
                return resp

            if method == "GET":
                nonce_entry = {
                    "id": "87654321-4321-4567-89ab-987654321abc",
                    "work": captured_nonce,
                    "struggle": "LTC verification challenge",
                    "intention": "Proving API ownership",
                    "created_at": "2026-01-01T00:00:00Z",
                }
                resp.status_code = 200
                all_entries = [valid_entry, nonce_entry]
                resp.json.return_value = {
                    "entries": all_entries,
                    "count": len(all_entries),
                }
                return resp

            return resp

        with (
            patch(
                "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
                autospec=True,
                side_effect=mock_fetch,
            ),
            patch(
                "learn_to_cloud_shared.verification.deployed_api._cleanup_challenge_entry",
                autospec=True,
            ),
        ):
            result = await validate_deployed_api("https://api.example.com")

            assert result.is_valid is True
            assert "ownership confirmed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_url_with_entries_suffix_normalized(self, _mock_ssrf):
        """URL ending in /entries should be normalized."""
        captured_nonce = None

        valid_entry = {
            "id": "12345678-1234-4567-89ab-123456789abc",
            "work": "Built an API",
            "struggle": "CORS issues",
            "intention": "Deploy to cloud",
            "created_at": "2025-01-25T10:30:00Z",
        }

        async def mock_fetch(url, *, method="GET", json_body=None):
            nonlocal captured_nonce
            resp = MagicMock(spec=httpx.Response)

            if method == "POST":
                assert json_body is not None
                captured_nonce = json_body["work"]
                resp.status_code = 200
                resp.json.return_value = {
                    "entry": {
                        "id": "87654321-4321-4567-89ab-987654321abc",
                        "work": captured_nonce,
                    }
                }
                return resp

            if method == "GET":
                nonce_entry = {
                    "id": "87654321-4321-4567-89ab-987654321abc",
                    "work": captured_nonce,
                    "struggle": "LTC verification challenge",
                    "intention": "Proving API ownership",
                    "created_at": "2026-01-01T00:00:00Z",
                }
                all_entries = [valid_entry, nonce_entry]
                resp.status_code = 200
                resp.json.return_value = {
                    "entries": all_entries,
                    "count": len(all_entries),
                }
                return resp

            return resp

        with (
            patch(
                "learn_to_cloud_shared.verification.deployed_api._fetch_with_retry",
                autospec=True,
                side_effect=mock_fetch,
            ) as mock,
            patch(
                "learn_to_cloud_shared.verification.deployed_api._cleanup_challenge_entry",
                autospec=True,
            ),
        ):
            result = await validate_deployed_api("https://api.example.com/entries")

            # Should call /entries (not /entries/entries)
            for call in mock.call_args_list:
                assert "/entries/entries" not in call.args[0]
            assert result.is_valid is True


@pytest.mark.unit
class TestIsPrivateIp:
    """Tests for _is_private_ip helper."""

    def test_loopback_ipv4(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_loopback_ipv6(self):
        assert _is_private_ip("::1") is True

    def test_private_10_range(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172_range(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_private_192_range(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.169.254") is True

    def test_multicast(self):
        assert _is_private_ip("224.0.0.1") is True

    def test_unspecified(self):
        assert _is_private_ip("0.0.0.0") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_public_ip_2(self):
        assert _is_private_ip("1.1.1.1") is False

    def test_invalid_string(self):
        assert _is_private_ip("not-an-ip") is True

    def test_cgnat_range(self):
        assert _is_private_ip("100.64.0.1") is True


@pytest.mark.unit
class TestValidateUrlTarget:
    """Tests for SSRF protection via _validate_url_target."""

    @pytest.mark.asyncio
    async def test_blocks_localhost(self):
        """URLs pointing to localhost should be blocked."""
        result = await _validate_url_target("https://127.0.0.1/entries")
        assert result is not None
        assert "publicly accessible" in result

    @pytest.mark.asyncio
    async def test_blocks_metadata_endpoint(self):
        """Cloud metadata endpoint (169.254.169.254) should be blocked."""
        result = await _validate_url_target("https://169.254.169.254/latest/meta-data/")
        assert result is not None
        assert "publicly accessible" in result

    @pytest.mark.asyncio
    async def test_blocks_private_10_range(self):
        """Private 10.x.x.x IPs should be blocked."""
        result = await _validate_url_target("https://10.0.0.1/entries")
        assert result is not None
        assert "publicly accessible" in result

    @pytest.mark.asyncio
    async def test_blocks_private_192_range(self):
        """Private 192.168.x.x IPs should be blocked."""
        result = await _validate_url_target("https://192.168.1.1/entries")
        assert result is not None
        assert "publicly accessible" in result

    @pytest.mark.asyncio
    async def test_blocks_dns_resolving_to_private(self):
        """Hostnames resolving to private IPs should be blocked."""
        with patch(
            "learn_to_cloud_shared.verification.deployed_api.asyncio.get_running_loop"
        ) as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]
            )
            result = await _validate_url_target("https://evil.example.com/entries")
            assert result is not None
            assert "publicly accessible" in result

    @pytest.mark.asyncio
    async def test_allows_dns_resolving_to_public(self):
        """Hostnames resolving to public IPs should be allowed."""
        with patch(
            "learn_to_cloud_shared.verification.deployed_api.asyncio.get_running_loop"
        ) as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[(2, 1, 6, "", ("20.50.2.100", 443))]
            )
            result = await _validate_url_target("https://myapi.azurewebsites.net")
            assert result is None

    @pytest.mark.asyncio
    async def test_blocks_unresolvable_host(self):
        """Hostnames that cannot be resolved should be blocked."""
        import socket as _socket

        with patch(
            "learn_to_cloud_shared.verification.deployed_api.asyncio.get_running_loop"
        ) as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                side_effect=_socket.gaierror("Name resolution failed")
            )
            result = await _validate_url_target("https://nonexistent.invalid/entries")
            assert result is not None
            assert "could not resolve" in result.lower()

    @pytest.mark.asyncio
    async def test_blocks_ipv6_loopback(self):
        """IPv6 loopback should be blocked."""
        result = await _validate_url_target("https://[::1]/entries")
        assert result is not None
        assert "publicly accessible" in result


@pytest.mark.unit
class TestSsrfIntegration:
    """Integration tests ensuring SSRF protection in validate_deployed_api."""

    @pytest.mark.asyncio
    async def test_rejects_private_ip_url(self):
        """validate_deployed_api should reject private IP URLs."""
        result = await validate_deployed_api("https://10.0.0.1")
        assert result.is_valid is False
        assert "publicly accessible" in result.message

    @pytest.mark.asyncio
    async def test_rejects_metadata_url(self):
        """validate_deployed_api should reject cloud metadata URLs."""
        result = await validate_deployed_api("https://169.254.169.254")
        assert result.is_valid is False
        assert "publicly accessible" in result.message

    @pytest.mark.asyncio
    async def test_rejects_localhost(self):
        """validate_deployed_api should reject localhost URLs."""
        result = await validate_deployed_api("https://127.0.0.1")
        assert result.is_valid is False
        assert "publicly accessible" in result.message

    @pytest.mark.asyncio
    async def test_rejects_cgnat_ip(self):
        """validate_deployed_api should reject CGNAT (100.64.0.0/10) URLs."""
        result = await validate_deployed_api("https://100.64.0.1")
        assert result.is_valid is False
        assert "publicly accessible" in result.message


@pytest.mark.unit
class TestCheckResponseIp:
    """Tests for post-connect SSRF validation via _check_response_ip."""

    def test_raises_on_private_ip(self):
        """Should raise _SsrfError when connected IP is private."""
        stream = MagicMock()
        stream.get_extra_info.return_value = ("10.0.0.1", 443)
        response = MagicMock(spec=httpx.Response)
        response.extensions = {"network_stream": stream}

        with pytest.raises(_SsrfError):
            _check_response_ip(response)

    def test_allows_public_ip(self):
        """Should not raise when connected IP is public."""
        stream = MagicMock()
        stream.get_extra_info.return_value = ("20.50.2.100", 443)
        response = MagicMock(spec=httpx.Response)
        response.extensions = {"network_stream": stream}

        _check_response_ip(response)  # Should not raise

    def test_no_stream_is_safe(self):
        """Should not raise when no network_stream (e.g. mocked response)."""
        response = MagicMock(spec=httpx.Response)
        response.extensions = {}

        _check_response_ip(response)  # Should not raise

    def test_raises_on_metadata_ip(self):
        """Should catch DNS rebinding to cloud metadata endpoint."""
        stream = MagicMock()
        stream.get_extra_info.return_value = ("169.254.169.254", 80)
        response = MagicMock(spec=httpx.Response)
        response.extensions = {"network_stream": stream}

        with pytest.raises(_SsrfError):
            _check_response_ip(response)


@pytest.mark.parametrize("status", [500, 503])
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_crud_exhaustion_retains_safe_status_after_three_requests(status, method):
    requests = []
    span = MagicMock()

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="private learner response body")

    operation = deployed_api._fetch_with_retry.retry_with(sleep=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)),
            patch.object(deployed_api.trace, "get_current_span", return_value=span),
        ):
            with pytest.raises(DeployedApiServerError) as raised:
                await operation("https://learner.example/entries", method=method)
            error = raised.value
            result = deployed_api.deployed_api_error_to_result(
                error, step="GET /entries"
            )
    assert len(requests) == 3
    assert [request.method for request in requests] == [method] * 3
    assert error.status_code == status
    assert error.retry_after is None
    assert str(error) == f"Server returned {status}"
    assert result.verification_completed
    assert not result.is_valid
    span.add_event.assert_called_once_with(
        "deployed_api.server_error",
        {
            "error.type": "server_error",
            "verification.operation": "GET /entries",
            "http.response.status_code": status,
        },
    )
    span.set_attribute.assert_any_call("http.response.status_code", status)
    assert "private learner" not in str(span.mock_calls)
    assert "learner.example" not in str(span.mock_calls)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
async def test_crud_nonserver_responses_are_not_newly_retried(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status)

    operation = deployed_api._fetch_with_retry.retry_with(sleep=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)):
            response = await operation("https://learner.example/entries")
    assert response.status_code == status
    assert len(requests) == 1


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
@pytest.mark.parametrize("retried", [False, True])
async def test_fetch_preserves_native_request_exceptions(error_type, retried):
    requests = []
    error = error_type("private transport detail")

    def handler(request):
        requests.append(request)
        raise error

    operation = (
        deployed_api._fetch_with_retry.retry_with(sleep=AsyncMock())
        if retried
        else deployed_api._fetch_once
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)),
            pytest.raises(error_type) as raised,
        ):
            await operation("https://learner.example/entries")
    assert raised.value is error
    assert len(requests) == (3 if retried else 1)


@pytest.mark.parametrize("failure", [500, 503, httpx.ReadTimeout, httpx.ConnectError])
async def test_live_analysis_failure_sends_exactly_one_request(failure):
    requests = []
    span = MagicMock()

    def handler(request):
        requests.append(request)
        if isinstance(failure, int):
            return httpx.Response(failure, text="private analysis details")
        raise failure("private analysis details")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)),
            patch.object(deployed_api.trace, "get_current_span", return_value=span),
        ):
            result = await deployed_api._verify_analysis(
                "https://learner.example", "challenge-id"
            )
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/entries/challenge-id/analyze"
    assert result.verification_completed
    assert not result.is_valid
    assert result.message.startswith("POST /entries/{id}/analyze:")
    assert "private" not in result.message
    assert "private" not in str(span.mock_calls)
    assert "learner.example" not in str(span.mock_calls)


@pytest.mark.parametrize(
    ("error", "category", "message"),
    [
        (
            httpx.ReadTimeout("private network detail"),
            "timeout",
            "Request timed out. Ensure your API is accessible and responding quickly.",
        ),
        (
            httpx.ConnectError("private network detail"),
            "request_error",
            "Could not connect to your API. Error: ConnectError",
        ),
    ],
)
def test_deployed_request_mapper_preserves_messages_and_completion(
    error, category, message
):
    span = MagicMock()
    with patch.object(deployed_api.trace, "get_current_span", return_value=span):
        result = deployed_api.deployed_api_error_to_result(error)
    assert result.message == message
    assert result.verification_completed
    assert not result.is_valid
    span.set_attribute.assert_called_once_with("error.type", category)
    span.add_event.assert_called_once_with(
        f"deployed_api.{category}",
        {"error.type": category, "verification.operation": "request"},
    )


def test_deployed_mapper_rethrows_unsupported_exception():
    error = ValueError("programming error")
    with pytest.raises(ValueError) as raised:
        deployed_api.deployed_api_error_to_result(error)
    assert raised.value is error
