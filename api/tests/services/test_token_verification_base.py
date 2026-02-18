"""Tests for token_verification_base shared utilities.

Tests cover:
- Token decoding (base64 + JSON parsing)
- Username verification (case-insensitive)
- Instance ID validation
- HMAC signature verification
- Challenge count validation
- Timestamp validation
- Secret derivation
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from services.token_verification_base import (
    decode_token,
    derive_secret,
    verify_challenge_count,
    verify_instance_id,
    verify_signature,
    verify_timestamp,
    verify_username,
)

# Same test secret used in conftest.py
TEST_SECRET = "test_ctf_secret_must_be_32_chars!"


def _derive_test_secret(instance_id: str) -> str:
    data = f"{TEST_SECRET}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def _make_token(payload: dict, signature: str) -> str:
    """Encode a token dict to base64."""
    return base64.b64encode(
        json.dumps({"payload": payload, "signature": signature}).encode()
    ).decode()


def _sign_payload(payload: dict, instance_id: str) -> str:
    """Compute HMAC-SHA256 for a payload."""
    secret = _derive_test_secret(instance_id)
    payload_str = json.dumps(payload, separators=(",", ":"))
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# decode_token
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDecodeToken:
    def test_valid_token(self):
        payload = {"github_username": "user", "instance_id": "abc"}
        sig = "deadbeef"
        token = _make_token(payload, sig)

        result = decode_token(token)
        assert result.is_valid
        assert result.payload == payload
        assert result.signature == sig

    def test_invalid_base64(self):
        result = decode_token("not-base64!!!")
        assert not result.is_valid
        assert "Could not decode" in (result.error or "")

    def test_invalid_json(self):
        token = base64.b64encode(b"not json").decode()
        result = decode_token(token)
        assert not result.is_valid
        assert "Could not decode" in (result.error or "")

    def test_missing_payload(self):
        token = base64.b64encode(json.dumps({"signature": "sig"}).encode()).decode()
        result = decode_token(token)
        assert not result.is_valid
        assert "Missing or malformed" in (result.error or "")

    def test_missing_signature(self):
        token = base64.b64encode(json.dumps({"payload": {"k": "v"}}).encode()).decode()
        result = decode_token(token)
        assert not result.is_valid
        assert "Missing or malformed" in (result.error or "")


# ---------------------------------------------------------------------------
# verify_username
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifyUsername:
    def test_matching_username(self):
        assert verify_username({"github_username": "TestUser"}, "testuser") is None

    def test_mismatched_username(self):
        err = verify_username({"github_username": "alice"}, "bob")
        assert err is not None
        assert "mismatch" in err.lower()

    def test_missing_username_in_payload(self):
        err = verify_username({}, "testuser")
        assert err is not None


# ---------------------------------------------------------------------------
# verify_instance_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifyInstanceId:
    def test_present(self):
        assert verify_instance_id({"instance_id": "abc-123"}) is None

    def test_missing(self):
        err = verify_instance_id({})
        assert err is not None
        assert "instance ID" in err


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifySignature:
    def test_valid_signature(self):
        payload = {"github_username": "user", "instance_id": "inst1"}
        sig = _sign_payload(payload, "inst1")

        err = verify_signature(payload, sig, "inst1")
        assert err is None

    def test_invalid_signature(self):
        payload = {"github_username": "user", "instance_id": "inst1"}

        err = verify_signature(payload, "badsig", "inst1")
        assert err is not None
        assert "tampered" in err.lower()

    def test_tampered_payload(self):
        payload = {"github_username": "user", "instance_id": "inst1", "challenges": 5}
        sig = _sign_payload(payload, "inst1")

        payload["challenges"] = 99
        err = verify_signature(payload, sig, "inst1")
        assert err is not None


# ---------------------------------------------------------------------------
# verify_challenge_count
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifyChallengeCount:
    def test_exact_match(self):
        assert verify_challenge_count({"challenges": 18}, 18) is None

    def test_too_few(self):
        err = verify_challenge_count({"challenges": 10}, 18, label="challenges")
        assert err is not None
        assert "10/18" in err

    def test_missing_defaults_to_zero(self):
        err = verify_challenge_count({}, 4, label="incidents")
        assert err is not None
        assert "0/4" in err


# ---------------------------------------------------------------------------
# verify_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifyTimestamp:
    def test_valid_timestamp(self):
        ts = datetime.now(UTC).timestamp()
        assert verify_timestamp({"timestamp": ts}) is None

    def test_future_timestamp(self):
        ts = datetime.now(UTC).timestamp() + 7200  # 2 hours ahead
        err = verify_timestamp({"timestamp": ts})
        assert err is not None
        assert "future" in err.lower()

    def test_missing_defaults_to_zero(self):
        # timestamp=0 is far in the past — should be fine
        assert verify_timestamp({}) is None


# ---------------------------------------------------------------------------
# derive_secret
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeriveSecret:
    def test_deterministic(self):
        s1 = derive_secret("instance-a")
        s2 = derive_secret("instance-a")
        assert s1 == s2

    def test_different_instances(self):
        s1 = derive_secret("instance-a")
        s2 = derive_secret("instance-b")
        assert s1 != s2

    def test_matches_manual_derivation(self):
        expected = _derive_test_secret("test-id")
        assert derive_secret("test-id") == expected
