"""Unit tests for ctf_service.

Tests cover:
- Valid CTF token verifies with 18 challenges
- Invalid token returns is_valid=False
- Config wiring: correct challenge count, label, and result type
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from services.ctf_service import verify_ctf_token

TEST_SECRET = "test_ctf_secret_must_be_32_chars!"


def _derive_test_secret(instance_id: str) -> str:
    data = f"{TEST_SECRET}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def _create_valid_ctf_token(
    github_username: str = "testuser",
    instance_id: str = "ctf-instance-1",
    challenges: int = 18,
    timestamp: float | None = None,
) -> str:
    if timestamp is None:
        timestamp = datetime.now(UTC).timestamp()

    payload = {
        "github_username": github_username,
        "instance_id": instance_id,
        "challenges": challenges,
        "timestamp": timestamp,
        "date": "2026-02-05",
        "time": "10:30:00",
    }

    secret = _derive_test_secret(instance_id)
    payload_str = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        secret.encode(), payload_str.encode(), hashlib.sha256
    ).hexdigest()

    token_data = {"payload": payload, "signature": signature}
    return base64.b64encode(json.dumps(token_data).encode()).decode()


@pytest.mark.unit
class TestVerifyCTFToken:
    def test_valid_token_succeeds(self):
        token = _create_valid_ctf_token(github_username="ctfuser")
        result = verify_ctf_token(token, "ctfuser")
        assert result.is_valid is True
        assert result.challenges_completed == 18
        assert "Congratulations" in result.message

    def test_username_mismatch_fails(self):
        token = _create_valid_ctf_token(github_username="alice")
        result = verify_ctf_token(token, "bob")
        assert result.is_valid is False
        assert "mismatch" in result.message.lower()

    def test_insufficient_challenges_fails(self):
        token = _create_valid_ctf_token(challenges=10)
        result = verify_ctf_token(token, "testuser")
        assert result.is_valid is False
        assert "10/18" in result.message

    def test_invalid_token_fails(self):
        result = verify_ctf_token("not-valid", "testuser")
        assert result.is_valid is False

    def test_returns_ctf_verification_result_type(self):
        from schemas import CTFVerificationResult

        token = _create_valid_ctf_token()
        result = verify_ctf_token(token, "testuser")
        assert isinstance(result, CTFVerificationResult)

    def test_case_insensitive_username(self):
        token = _create_valid_ctf_token(github_username="TestUser")
        result = verify_ctf_token(token, "testuser")
        assert result.is_valid is True
