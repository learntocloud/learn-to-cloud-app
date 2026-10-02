"""Unit tests for networking lab token verification.

Tests the Networking Lab-specific token verification wiring:
- Accepted provider challenge types and cloud_provider extraction
- Incomplete incidents
- Empty/whitespace token edge cases
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from learn_to_cloud.verification.token_base import (
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

    @pytest.mark.parametrize(
        "challenge_type,expected_provider",
        [
            ("networking-lab-azure", "azure"),
            ("networking-lab-aws", "aws"),
            ("networking-lab-gcp", "gcp"),
        ],
    )
    def test_all_provider_challenge_types_succeed(
        self, challenge_type, expected_provider
    ):
        """Tokens from any provider variant should verify."""
        token = _create_valid_token(
            github_username="testuser",
            challenge_type=challenge_type,
        )

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.cloud_provider == expected_provider

    def test_incomplete_challenges_fails(self):
        """Token with fewer than required challenges should fail."""
        token = _create_valid_token(
            github_username="testuser",
            challenges=2,
        )

        result = verify_networking_token(token, "testuser")

        assert result.is_valid is False
        assert "Incomplete" in result.message
        assert f"2/{REQUIRED_CHALLENGES}" in result.message


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

    def test_valid_token_has_cloud_provider(self):
        """Successful verification should populate cloud_provider."""
        token = _create_valid_token(
            github_username="fulltest",
            challenges=4,
        )

        result = verify_networking_token(token, "fulltest")

        assert result.is_valid is True
        assert result.cloud_provider == "azure"
