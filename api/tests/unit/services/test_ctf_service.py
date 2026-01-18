"""Tests for services/ctf_service.py - CTF token verification."""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import patch

import pytest

from services.ctf_service import (
    REQUIRED_CHALLENGES,
    CTFVerificationResult,
    _derive_secret,
    _get_master_secret,
    verify_ctf_token,
)


def _create_valid_token(
    github_username: str,
    instance_id: str = "test-instance-123",
    challenges: int = 18,
    timestamp: float | None = None,
    master_secret: str = "test-master-secret",
) -> str:
    """Helper to create a valid CTF token for testing."""
    if timestamp is None:
        timestamp = datetime.now().timestamp()

    payload = {
        "github_username": github_username,
        "instance_id": instance_id,
        "challenges": challenges,
        "timestamp": timestamp,
        "date": "2026-01-17",
        "time": "10:30:00",
    }

    # Derive verification secret same way the real code does
    data = f"{master_secret}:{instance_id}"
    verification_secret = hashlib.sha256(data.encode()).hexdigest()

    # Sign payload
    payload_str = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        verification_secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    token_data = {"payload": payload, "signature": signature}
    return base64.b64encode(json.dumps(token_data).encode()).decode()


class TestCTFConstants:
    """Test CTF constants."""

    def test_required_challenges_is_18(self):
        """REQUIRED_CHALLENGES should be 18."""
        assert REQUIRED_CHALLENGES == 18


class TestGetMasterSecret:
    """Tests for _get_master_secret."""

    @patch("services.ctf_service.get_settings")
    def test_returns_configured_secret(self, mock_settings):
        """Returns the configured CTF master secret."""
        mock_settings.return_value.ctf_master_secret = "my-secret-key"
        mock_settings.return_value.environment = "development"
        assert _get_master_secret() == "my-secret-key"

    @patch("services.ctf_service.get_settings")
    def test_production_requires_non_default_secret(self, mock_settings):
        """Production environment rejects default secret."""
        mock_settings.return_value.ctf_master_secret = "L2C_CTF_MASTER_2024"
        mock_settings.return_value.environment = "production"
        with pytest.raises(RuntimeError, match="CTF master secret is not configured"):
            _get_master_secret()

    @patch("services.ctf_service.get_settings")
    def test_production_rejects_empty_secret(self, mock_settings):
        """Production environment rejects empty secret."""
        mock_settings.return_value.ctf_master_secret = ""
        mock_settings.return_value.environment = "production"
        with pytest.raises(RuntimeError, match="CTF master secret is not configured"):
            _get_master_secret()

    @patch("services.ctf_service.get_settings")
    def test_development_allows_default_secret(self, mock_settings):
        """Development environment allows default secret."""
        mock_settings.return_value.ctf_master_secret = "L2C_CTF_MASTER_2024"
        mock_settings.return_value.environment = "development"
        # Should not raise
        result = _get_master_secret()
        assert result == "L2C_CTF_MASTER_2024"


class TestDeriveSecret:
    """Tests for _derive_secret."""

    @patch("services.ctf_service.get_settings")
    def test_derives_deterministic_secret(self, mock_settings):
        """Same inputs produce same derived secret."""
        mock_settings.return_value.ctf_master_secret = "master"
        mock_settings.return_value.environment = "development"

        result1 = _derive_secret("instance-1")
        result2 = _derive_secret("instance-1")
        assert result1 == result2

    @patch("services.ctf_service.get_settings")
    def test_different_instances_produce_different_secrets(self, mock_settings):
        """Different instance IDs produce different secrets."""
        mock_settings.return_value.ctf_master_secret = "master"
        mock_settings.return_value.environment = "development"

        result1 = _derive_secret("instance-1")
        result2 = _derive_secret("instance-2")
        assert result1 != result2

    @patch("services.ctf_service.get_settings")
    def test_secret_is_sha256_hex(self, mock_settings):
        """Derived secret is a 64-char hex string (SHA256)."""
        mock_settings.return_value.ctf_master_secret = "master"
        mock_settings.return_value.environment = "development"

        result = _derive_secret("instance-1")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestVerifyCTFToken:
    """Tests for verify_ctf_token."""

    @patch("services.ctf_service.get_settings")
    def test_valid_token_passes(self, mock_settings):
        """Valid token with matching username and all challenges passes."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        token = _create_valid_token("testuser")
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.github_username == "testuser"
        assert result.challenges_completed == 18
        assert result.completion_date == "2026-01-17"

    @patch("services.ctf_service.get_settings")
    def test_case_insensitive_username_match(self, mock_settings):
        """Username comparison is case-insensitive."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        token = _create_valid_token("TestUser")
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is True

    @patch("services.ctf_service.get_settings")
    def test_username_mismatch_fails(self, mock_settings):
        """Token for different user fails."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        token = _create_valid_token("alice")
        result = verify_ctf_token(token, "bob")

        assert result.is_valid is False
        assert "username mismatch" in result.message.lower()

    def test_invalid_base64_fails(self):
        """Invalid base64 encoding fails."""
        result = verify_ctf_token("not-valid-base64!!!", "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_invalid_json_fails(self):
        """Valid base64 but invalid JSON fails."""
        token = base64.b64encode(b"not json").decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_missing_payload_fails(self):
        """Token without payload field fails."""
        token_data = {"signature": "abc123"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing payload or signature" in result.message

    def test_missing_signature_fails(self):
        """Token without signature field fails."""
        token_data = {"payload": {"github_username": "testuser"}}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing payload or signature" in result.message

    @patch("services.ctf_service.get_settings")
    def test_missing_instance_id_fails(self, mock_settings):
        """Token without instance_id fails."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        payload = {"github_username": "testuser"}  # No instance_id
        token_data = {"payload": payload, "signature": "fake"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "missing instance ID" in result.message

    @patch("services.ctf_service.get_settings")
    def test_invalid_signature_fails(self, mock_settings):
        """Token with invalid signature fails."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        payload = {
            "github_username": "testuser",
            "instance_id": "test-instance",
            "challenges": 18,
            "timestamp": datetime.now().timestamp(),
        }
        token_data = {"payload": payload, "signature": "invalid-signature"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Invalid token signature" in result.message

    @patch("services.ctf_service.get_settings")
    def test_incomplete_challenges_fails(self, mock_settings):
        """Token with fewer than 18 challenges fails."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        token = _create_valid_token("testuser", challenges=10)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Incomplete challenges" in result.message
        assert "10/18" in result.message

    @patch("services.ctf_service.get_settings")
    def test_future_timestamp_fails(self, mock_settings):
        """Token with timestamp too far in future fails."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        # Timestamp 2 hours in the future (beyond 1 hour tolerance)
        future_timestamp = datetime.now().timestamp() + 7200
        token = _create_valid_token("testuser", timestamp=future_timestamp)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "future" in result.message.lower()

    @patch("services.ctf_service.get_settings")
    def test_timestamp_slightly_in_future_passes(self, mock_settings):
        """Token with timestamp slightly in future (within tolerance) passes."""
        mock_settings.return_value.ctf_master_secret = "test-master-secret"
        mock_settings.return_value.environment = "development"

        # Timestamp 30 minutes in the future (within 1 hour tolerance)
        future_timestamp = datetime.now().timestamp() + 1800
        token = _create_valid_token("testuser", timestamp=future_timestamp)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is True

    @patch("services.ctf_service.get_settings")
    def test_production_misconfiguration_returns_error(self, mock_settings):
        """Production with bad secret returns user-friendly error."""
        mock_settings.return_value.ctf_master_secret = "L2C_CTF_MASTER_2024"
        mock_settings.return_value.environment = "production"

        # Create token (will use wrong secret but that's fine)
        payload = {
            "github_username": "testuser",
            "instance_id": "test-instance",
            "challenges": 18,
            "timestamp": datetime.now().timestamp(),
        }
        token_data = {"payload": payload, "signature": "fake"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "not available" in result.message


class TestCTFVerificationResult:
    """Tests for CTFVerificationResult dataclass."""

    def test_default_values(self):
        """Optional fields default to None."""
        result = CTFVerificationResult(is_valid=False, message="Test")
        assert result.github_username is None
        assert result.completion_date is None
        assert result.completion_time is None
        assert result.challenges_completed is None

    def test_all_fields(self):
        """All fields can be set."""
        result = CTFVerificationResult(
            is_valid=True,
            message="Success",
            github_username="testuser",
            completion_date="2026-01-17",
            completion_time="10:30:00",
            challenges_completed=18,
        )
        assert result.is_valid is True
        assert result.github_username == "testuser"
        assert result.challenges_completed == 18
