"""Tests for CTF token verification."""

import base64
import hashlib
import hmac
import json
import time

from services.ctf import (
    REQUIRED_CHALLENGES,
    CTFVerificationResult,
    verify_ctf_token,
)

TEST_MASTER_SECRET = "L2C_CTF_MASTER_2024"


def derive_secret(instance_id: str) -> str:
    """Derive verification secret (same as in ctf.py)."""
    data = f"{TEST_MASTER_SECRET}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def create_token(
    github_username: str = "testuser",
    challenges: int = 18,
    instance_id: str = "test-instance-123",
    timestamp: float | None = None,
    date: str = "2024-01-15",
    completion_time: str = "12:30:45",
    tamper_signature: bool = False,
    tamper_payload: bool = False,
) -> str:
    """Create a test CTF token.

    Args:
        github_username: GitHub username in the token
        challenges: Number of challenges completed
        instance_id: Instance ID for secret derivation
        timestamp: Unix timestamp (defaults to now)
        date: Completion date string
        completion_time: Completion time string
        tamper_signature: If True, use wrong signature
        tamper_payload: If True, modify payload after signing

    Returns:
        Base64-encoded token string
    """
    if timestamp is None:
        timestamp = time.time()

    payload = {
        "github_username": github_username,
        "date": date,
        "time": completion_time,
        "challenges": challenges,
        "instance_id": instance_id,
        "timestamp": timestamp,
    }

    verification_secret = derive_secret(instance_id)
    payload_str = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        verification_secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    if tamper_signature:
        signature = "tampered" + signature[8:]

    if tamper_payload:
        payload["challenges"] = 99

    token_data = {"payload": payload, "signature": signature}
    return base64.b64encode(json.dumps(token_data).encode()).decode()


class TestVerifyCtfToken:
    """Tests for verify_ctf_token function."""

    def test_valid_token_matching_username(self):
        """Valid token with matching username should pass."""
        token = create_token(github_username="testuser")
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.github_username == "testuser"
        assert result.challenges_completed == 18

    def test_valid_token_case_insensitive_username(self):
        """Username comparison should be case-insensitive."""
        token = create_token(github_username="TestUser")
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is True

        token2 = create_token(github_username="testuser")
        result2 = verify_ctf_token(token2, "TESTUSER")

        assert result2.is_valid is True

    def test_username_mismatch(self):
        """Token with mismatched username should fail."""
        token = create_token(github_username="alice")
        result = verify_ctf_token(token, "bob")

        assert result.is_valid is False
        assert "mismatch" in result.message.lower()
        assert "alice" in result.message
        assert "bob" in result.message

    def test_invalid_base64(self):
        """Invalid base64 should fail gracefully."""
        result = verify_ctf_token("not-valid-base64!!!", "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_invalid_json(self):
        """Valid base64 but invalid JSON should fail."""
        invalid_token = base64.b64encode(b"not json").decode()
        result = verify_ctf_token(invalid_token, "testuser")

        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_missing_payload(self):
        """Token without payload should fail."""
        token_data = {"signature": "abc123"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing payload" in result.message or "Invalid token" in result.message

    def test_missing_signature(self):
        """Token without signature should fail."""
        token_data = {"payload": {"github_username": "testuser"}}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Missing" in result.message or "Invalid token" in result.message

    def test_missing_instance_id(self):
        """Token without instance_id should fail."""
        payload = {
            "github_username": "testuser",
            "challenges": 18,
        }
        token_data = {"payload": payload, "signature": "fake"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "instance" in result.message.lower()

    def test_tampered_signature(self):
        """Token with tampered signature should fail."""
        token = create_token(tamper_signature=True)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "signature" in result.message.lower()

    def test_tampered_payload(self):
        """Token with tampered payload should fail signature check."""
        token = create_token(tamper_payload=True)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "signature" in result.message.lower()

    def test_incomplete_challenges(self):
        """Token with fewer than 18 challenges should fail."""
        token = create_token(challenges=15)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "15" in result.message
        assert str(REQUIRED_CHALLENGES) in result.message

    def test_zero_challenges(self):
        """Token with zero challenges should fail."""
        token = create_token(challenges=0)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "Incomplete" in result.message or "0" in result.message

    def test_future_timestamp(self):
        """Token with future timestamp should fail."""
        future_time = time.time() + 7200
        token = create_token(timestamp=future_time)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is False
        assert "future" in result.message.lower()

    def test_past_timestamp_ok(self):
        """Token with past timestamp should be fine."""
        past_time = time.time() - 86400
        token = create_token(timestamp=past_time)
        result = verify_ctf_token(token, "testuser")

        assert result.is_valid is True

    def test_result_contains_completion_data(self):
        """Valid result should contain completion metadata."""
        token = create_token(
            github_username="developer",
            date="2024-03-15",
            completion_time="14:30:00",
        )
        result = verify_ctf_token(token, "developer")

        assert result.is_valid is True
        assert result.github_username == "developer"
        assert result.completion_date == "2024-03-15"
        assert result.completion_time == "14:30:00"
        assert result.challenges_completed == 18

    def test_empty_token(self):
        """Empty token should fail."""
        result = verify_ctf_token("", "testuser")

        assert result.is_valid is False

    def test_empty_username(self):
        """Empty OAuth username should still process."""
        token = create_token(github_username="testuser")
        result = verify_ctf_token(token, "")

        assert result.is_valid is False
        assert "mismatch" in result.message.lower()


class TestCtfVerificationResult:
    """Tests for CTFVerificationResult dataclass."""

    def test_default_values(self):
        """Test default values for optional fields."""
        result = CTFVerificationResult(is_valid=False, message="Test")

        assert result.is_valid is False
        assert result.message == "Test"
        assert result.github_username is None
        assert result.completion_date is None
        assert result.completion_time is None
        assert result.challenges_completed is None

    def test_all_fields(self):
        """Test result with all fields populated."""
        result = CTFVerificationResult(
            is_valid=True,
            message="Success!",
            github_username="dev",
            completion_date="2024-01-01",
            completion_time="10:00:00",
            challenges_completed=18,
        )

        assert result.is_valid is True
        assert result.github_username == "dev"
        assert result.challenges_completed == 18
