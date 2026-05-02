"""Tests for token_base shared verification.

Tests cover the core verify_lab_token function and secret derivation.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from learn_to_cloud.services.verification.token_base import verify_lab_token

# Same test secret used in conftest.py
TEST_SECRET = "test_ctf_secret_must_be_32_chars!"


def _derive_test_secret(instance_id: str) -> str:
    data = f"{TEST_SECRET}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def _make_signed_token(
    payload: dict,
    instance_id: str | None = None,
) -> str:
    """Create a signed token. If instance_id is None, uses payload's instance_id."""
    iid = instance_id or payload.get("instance_id", "test-inst")
    secret = _derive_test_secret(iid)
    payload_str = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    token_data = {"payload": payload, "signature": sig}
    return base64.b64encode(json.dumps(token_data).encode()).decode()


def _valid_payload(**overrides) -> dict:
    defaults = {
        "github_username": "testuser",
        "instance_id": "test-inst",
        "challenges": 5,
        "timestamp": datetime.now(UTC).timestamp(),
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.unit
class TestVerifyLabToken:
    def test_valid_token(self):
        payload = _valid_payload()
        token = _make_signed_token(payload)
        result = verify_lab_token(
            token, "testuser", required_challenges=5, display_name="Test"
        )
        assert result.is_valid is True

    def test_invalid_base64(self):
        result = verify_lab_token("not-base64!!!", "testuser", required_challenges=5)
        assert result.is_valid is False
        assert "Could not decode" in result.message

    def test_invalid_json(self):
        token = base64.b64encode(b"not json").decode()
        result = verify_lab_token(token, "testuser", required_challenges=5)
        assert result.is_valid is False

    def test_missing_payload(self):
        token = base64.b64encode(json.dumps({"signature": "x"}).encode()).decode()
        result = verify_lab_token(token, "testuser", required_challenges=5)
        assert result.is_valid is False
        assert "Missing or malformed" in result.message

    def test_username_mismatch(self):
        payload = _valid_payload(github_username="alice")
        token = _make_signed_token(payload)
        result = verify_lab_token(token, "bob", required_challenges=5)
        assert result.is_valid is False
        assert "mismatch" in result.message.lower()

    def test_case_insensitive_username(self):
        payload = _valid_payload(github_username="TestUser")
        token = _make_signed_token(payload)
        result = verify_lab_token(token, "testuser", required_challenges=5)
        assert result.is_valid is True

    def test_missing_instance_id(self):
        payload = _valid_payload()
        del payload["instance_id"]
        token = base64.b64encode(
            json.dumps({"payload": payload, "signature": "x"}).encode()
        ).decode()
        result = verify_lab_token(token, "testuser", required_challenges=5)
        assert result.is_valid is False
        assert "instance ID" in result.message

    def test_bad_signature(self):
        payload = _valid_payload()
        token_data = {"payload": payload, "signature": "badsig"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        result = verify_lab_token(token, "testuser", required_challenges=5)
        assert result.is_valid is False
        assert "tampered" in result.message.lower()

    def test_wrong_challenge_count(self):
        payload = _valid_payload(challenges=3)
        token = _make_signed_token(payload)
        result = verify_lab_token(
            token, "testuser", required_challenges=5, challenge_label="tasks"
        )
        assert result.is_valid is False
        assert "3/5" in result.message

    def test_future_timestamp(self):
        payload = _valid_payload(timestamp=datetime.now(UTC).timestamp() + 7200)
        token = _make_signed_token(payload)
        result = verify_lab_token(token, "testuser", required_challenges=5)
        assert result.is_valid is False
        assert "future" in result.message.lower()

    def test_challenge_type_filtering(self):
        payload = _valid_payload(challenge="networking-lab-azure")
        token = _make_signed_token(payload)
        result = verify_lab_token(
            token,
            "testuser",
            required_challenges=5,
            accepted_challenge_types=frozenset({"networking-lab-azure"}),
        )
        assert result.is_valid is True
        assert result.cloud_provider == "azure"

    def test_wrong_challenge_type(self):
        payload = _valid_payload(challenge="wrong-type")
        token = _make_signed_token(payload)
        result = verify_lab_token(
            token,
            "testuser",
            required_challenges=5,
            accepted_challenge_types=frozenset({"networking-lab-azure"}),
        )
        assert result.is_valid is False
        assert "Invalid challenge type" in result.message
