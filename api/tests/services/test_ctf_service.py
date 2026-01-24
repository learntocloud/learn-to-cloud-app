"""Tests for CTF token verification service."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from services.ctf_service import (
    REQUIRED_CHALLENGES,
    _derive_secret,
    _get_master_secret,
    verify_ctf_token,
)

pytestmark = pytest.mark.unit


class TestGetMasterSecret:
    """Tests for _get_master_secret function."""

    def test_returns_configured_secret(self):
        """Test returns secret from settings."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "test-secret-123"
            mock_settings.return_value.environment = "development"

            secret = _get_master_secret()
            assert secret == "test-secret-123"

    def test_raises_in_production_with_default_secret(self):
        """Test raises error in production with default secret."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "L2C_CTF_MASTER_2024"
            mock_settings.return_value.environment = "production"

            with pytest.raises(RuntimeError, match="not configured"):
                _get_master_secret()

    def test_raises_in_production_with_empty_secret(self):
        """Test raises error in production with empty secret."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = ""
            mock_settings.return_value.environment = "production"

            with pytest.raises(RuntimeError, match="not configured"):
                _get_master_secret()

    def test_allows_default_in_development(self):
        """Test allows default secret in development."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "L2C_CTF_MASTER_2024"
            mock_settings.return_value.environment = "development"

            secret = _get_master_secret()
            assert secret == "L2C_CTF_MASTER_2024"


class TestDeriveSecret:
    """Tests for _derive_secret function."""

    def test_derives_secret_from_instance_id(self):
        """Test derives secret using SHA256."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "master-secret"
            mock_settings.return_value.environment = "development"

            secret = _derive_secret("instance-123")

            # Verify it's a valid SHA256 hex digest
            assert len(secret) == 64
            assert all(c in "0123456789abcdef" for c in secret)

    def test_different_instances_get_different_secrets(self):
        """Test different instance IDs produce different secrets."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "master-secret"
            mock_settings.return_value.environment = "development"

            secret1 = _derive_secret("instance-1")
            secret2 = _derive_secret("instance-2")

            assert secret1 != secret2


class TestVerifyCTFToken:
    """Tests for verify_ctf_token function."""

    def _create_valid_token(
        self,
        github_username: str,
        instance_id: str = "test-instance",
        challenges: int = REQUIRED_CHALLENGES,
        timestamp: float | None = None,
    ) -> str:
        """Helper to create a valid CTF token."""
        if timestamp is None:
            timestamp = datetime.now(UTC).timestamp()

        payload = {
            "github_username": github_username,
            "instance_id": instance_id,
            "challenges": challenges,
            "timestamp": timestamp,
            "date": "2025-01-24",
            "time": "12:00:00",
        }

        # Derive secret the same way the service does
        master_secret = "test-master-secret"
        data = f"{master_secret}:{instance_id}"
        verification_secret = hashlib.sha256(data.encode()).hexdigest()

        payload_str = json.dumps(payload, separators=(",", ":"))
        signature = hmac.new(
            verification_secret.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        token_data = {"payload": payload, "signature": signature}
        return base64.b64encode(json.dumps(token_data).encode()).decode()

    def test_returns_invalid_for_malformed_base64(self):
        """Test returns invalid for non-base64 token."""
        result = verify_ctf_token("not-valid-base64!!!", "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_returns_invalid_for_malformed_json(self):
        """Test returns invalid for non-JSON content."""
        token = base64.b64encode(b"not json").decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_returns_invalid_for_missing_payload(self):
        """Test returns invalid when payload is missing."""
        token_data = {"signature": "abc123"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing payload or signature" in result.message

    def test_returns_invalid_for_missing_signature(self):
        """Test returns invalid when signature is missing."""
        token_data = {"payload": {"github_username": "testuser"}}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing payload or signature" in result.message

    def test_returns_invalid_for_username_mismatch(self):
        """Test returns invalid when GitHub username doesn't match."""
        token_data = {
            "payload": {"github_username": "alice", "instance_id": "test"},
            "signature": "abc123",
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "bob")

        assert result.is_valid is False
        assert "username mismatch" in result.message.lower()

    def test_username_comparison_is_case_insensitive(self):
        """Test username comparison ignores case."""
        token_data = {
            "payload": {"github_username": "TestUser", "instance_id": "test"},
            "signature": "abc123",
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        # Should NOT fail on username mismatch - will fail on signature instead
        result = verify_ctf_token(token, "TESTUSER")

        # If it were a username mismatch, message would say so
        assert "username mismatch" not in result.message.lower()

    def test_returns_invalid_for_missing_instance_id(self):
        """Test returns invalid when instance_id is missing."""
        token_data = {
            "payload": {"github_username": "testuser"},
            "signature": "abc123",
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "missing instance ID" in result.message

    def test_returns_invalid_when_master_secret_not_configured(self):
        """Test returns invalid when secret isn't configured in production."""
        token_data = {
            "payload": {"github_username": "testuser", "instance_id": "test-id"},
            "signature": "abc123",
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = ""
            mock_settings.return_value.environment = "production"

            result = verify_ctf_token(token, "testuser")

            assert result.is_valid is False
            assert "not available" in result.message

    def test_returns_invalid_for_bad_signature(self):
        """Test returns invalid when signature doesn't match."""
        token_data = {
            "payload": {
                "github_username": "testuser",
                "instance_id": "test-id",
                "challenges": 18,
                "timestamp": datetime.now(UTC).timestamp(),
            },
            "signature": "invalid-signature",
        }
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "test-secret"
            mock_settings.return_value.environment = "development"

            result = verify_ctf_token(token, "testuser")

            assert result.is_valid is False
            assert "Invalid token signature" in result.message

    def test_returns_invalid_for_incomplete_challenges(self):
        """Test returns invalid when not all challenges completed."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "test-master-secret"
            mock_settings.return_value.environment = "development"

            token = self._create_valid_token("testuser", challenges=10)
            result = verify_ctf_token(token, "testuser")

            assert result.is_valid is False
            assert "Incomplete challenges" in result.message
            assert "10/18" in result.message

    def test_returns_invalid_for_future_timestamp(self):
        """Test returns invalid when timestamp is too far in the future."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "test-master-secret"
            mock_settings.return_value.environment = "development"

            # Set timestamp 2 hours in the future (beyond 1 hour tolerance)
            future_time = datetime.now(UTC).timestamp() + 7200
            token = self._create_valid_token("testuser", timestamp=future_time)

            result = verify_ctf_token(token, "testuser")

            assert result.is_valid is False
            assert "future" in result.message.lower()

    def test_returns_valid_for_correct_token(self):
        """Test returns valid for properly signed token with all requirements."""
        with patch("services.ctf_service.get_settings") as mock_settings:
            mock_settings.return_value.ctf_master_secret = "test-master-secret"
            mock_settings.return_value.environment = "development"

            token = self._create_valid_token("testuser")
            result = verify_ctf_token(token, "testuser")

            assert result.is_valid is True
            assert "Congratulations" in result.message
            assert result.github_username == "testuser"
            assert result.challenges_completed == REQUIRED_CHALLENGES

    def test_handles_unexpected_exceptions(self):
        """Test handles malformed tokens gracefully."""
        # When passed a non-base64 token, it catches the decode error
        result = verify_ctf_token("not-valid-base64-token!!!", "testuser")

        assert result.is_valid is False
        assert "invalid token format" in result.message.lower()
