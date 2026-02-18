"""Unit tests for networking_lab_service.

Tests the Networking Lab token verification logic:
- Valid token with correct HMAC signature
- Invalid token formats (not base64, not JSON)
- Missing payload/signature
- Challenge type mismatch
- Username mismatch
- Incomplete incidents
- Invalid HMAC signature
- Future timestamp detection
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from services.networking_lab_service import (
    ACCEPTED_CHALLENGE_TYPES,
    REQUIRED_CHALLENGES,
    verify_networking_token,
)

# Test secret configured in conftest.py
TEST_SECRET = "test_ctf_secret_must_be_32_chars!"


def _derive_test_secret(instance_id: str) -> str:
    """Derive verification secret the same way the service does."""
    data = f"{TEST_SECRET}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def _create_valid_token(
    github_username: str = "testuser",
    instance_id: str = "test-instance-123",
    challenges: int = REQUIRED_CHALLENGES,
    challenge_type: str = "networking-lab-azure",
    timestamp: float | None = None,
) -> str:
    """Create a valid networking lab token for testing."""
    if timestamp is None:
        timestamp = datetime.now(UTC).timestamp()

    payload = {
        "github_username": github_username,
        "instance_id": instance_id,
        "challenges": challenges,
        "challenge": challenge_type,
        "timestamp": timestamp,
        "date": "2026-02-05",
        "time": "10:30:00",
    }

    # Sign the payload
    verification_secret = _derive_test_secret(instance_id)
    payload_str = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        verification_secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    token_data = {"payload": payload, "signature": signature}
    return base64.b64encode(json.dumps(token_data).encode()).decode()


@pytest.mark.unit
class TestVerifyNetworkingToken:
    """Tests for verify_networking_token function."""

    def test_valid_token_succeeds(self):
        """A properly signed token with all requirements should verify."""
        token = _create_valid_token(github_username="validuser")
        result = verify_networking_token(token, "validuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.github_username == "validuser"
        assert result.challenges_completed == REQUIRED_CHALLENGES
        assert result.challenge_type in ACCEPTED_CHALLENGE_TYPES

    def test_valid_token_case_insensitive_username(self):
        """Username comparison should be case-insensitive."""
        token = _create_valid_token(github_username="TestUser")
        result = verify_networking_token(token, "testuser")

        assert result.is_valid is True

    def test_invalid_base64_fails(self):
        """Non-base64 input should fail gracefully."""
        result = verify_networking_token("not-valid-base64!!!", "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_invalid_json_fails(self):
        """Valid base64 but invalid JSON should fail."""
        invalid_json = base64.b64encode(b"not json").decode()
        result = verify_networking_token(invalid_json, "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_missing_payload_fails(self):
        """Token without payload field should fail."""
        token_data = {"signature": "somesig"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing or malformed" in result.message

    def test_missing_signature_fails(self):
        """Token without signature field should fail."""
        token_data = {"payload": {"github_username": "test"}}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing or malformed" in result.message

    def test_wrong_challenge_type_fails(self):
        """Token with wrong challenge type should fail."""
        token = _create_valid_token(
            github_username="testuser",
            challenge_type="wrong-challenge-type",
        )

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "Invalid challenge type" in result.message

    @pytest.mark.parametrize(
        "challenge_type",
        ["networking-lab-azure", "networking-lab-aws", "networking-lab-gcp"],
    )
    def test_all_provider_challenge_types_succeed(self, challenge_type: str):
        """Tokens from any provider variant should verify."""
        token = _create_valid_token(
            github_username="testuser",
            challenge_type=challenge_type,
        )

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.challenge_type == challenge_type

    def test_username_mismatch_fails(self):
        """Token username must match OAuth username."""
        token = _create_valid_token(github_username="differentuser")

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "username mismatch" in result.message.lower()
        assert "differentuser" in result.message
        assert "testuser" in result.message

    def test_incomplete_challenges_fails(self):
        """Token with fewer than required challenges should fail."""
        token = _create_valid_token(
            github_username="testuser",
            challenges=2,  # Less than REQUIRED_CHALLENGES (4)
        )

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "Incomplete" in result.message
        assert f"2/{REQUIRED_CHALLENGES}" in result.message

    def test_invalid_signature_fails(self):
        """Tampered signature should fail verification."""
        # Create a valid token
        token_str = _create_valid_token(github_username="testuser")

        # Decode, tamper with signature, re-encode
        token_data = json.loads(base64.b64decode(token_str))
        token_data["signature"] = "tampered" + token_data["signature"][8:]
        tampered_token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_networking_token(tampered_token, "testuser")

        assert result.is_valid is False
        assert "Invalid token signature" in result.message

    def test_tampered_payload_fails(self):
        """Modifying payload after signing should fail."""
        # Create a valid token
        token_str = _create_valid_token(github_username="testuser", challenges=4)

        # Decode, tamper with payload (change challenges), re-encode
        token_data = json.loads(base64.b64decode(token_str))
        token_data["payload"]["challenges"] = 99  # Tamper
        tampered_token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_networking_token(tampered_token, "testuser")

        assert result.is_valid is False
        assert "Invalid token signature" in result.message

    def test_future_timestamp_fails(self):
        """Token from far in the future should be rejected."""
        # Set timestamp 2 hours in the future (beyond 1-hour tolerance)
        future_timestamp = datetime.now(UTC).timestamp() + 7200

        token = _create_valid_token(
            github_username="testuser",
            timestamp=future_timestamp,
        )

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "future" in result.message.lower()

    def test_missing_instance_id_fails(self):
        """Token without instance_id should fail."""
        payload = {
            "github_username": "testuser",
            # Missing instance_id
            "challenges": 4,
            "challenge": "networking-lab-azure",
            "timestamp": datetime.now(UTC).timestamp(),
        }

        token_data = {"payload": payload, "signature": "dummy"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "instance ID" in result.message


@pytest.mark.unit
class TestNetworkingTokenEdgeCases:
    """Edge case tests for networking token verification."""

    def test_empty_token_fails(self):
        """Empty string token should fail."""
        result = verify_networking_token("", "testuser")

        assert result.is_valid is False

    def test_whitespace_token_fails(self):
        """Whitespace-only token should fail."""
        result = verify_networking_token("   ", "testuser")

        assert result.is_valid is False

    def test_empty_username_in_token_fails(self):
        """Token with empty github_username should fail (mismatch)."""
        token = _create_valid_token(github_username="")

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "mismatch" in result.message.lower()

    def test_verification_result_fields(self):
        """Successful verification should populate all result fields."""
        token = _create_valid_token(
            github_username="fulltest",
            challenges=4,
        )

        result = verify_networking_token(token, "fulltest")

        assert result.is_valid is True
        assert result.github_username == "fulltest"
        assert result.challenges_completed == 4
        assert result.challenge_type in ACCEPTED_CHALLENGE_TYPES
        assert result.completion_date is not None
        assert result.completion_time is not None
