"""Unit tests for iac_lab_service.

Tests IaC lab token verification logic:
- Valid Azure/AWS/GCP token verification
- Invalid token formats/signatures
- Username mismatch handling
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from services.iac_lab_service import (
    ACCEPTED_CHALLENGE_TYPES,
    REQUIRED_CHALLENGES_BY_TYPE,
    verify_iac_token,
)

TEST_SECRET = "test_ctf_secret_must_be_32_chars!"


def _derive_test_secret(instance_id: str) -> str:
    data = f"{TEST_SECRET}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def _create_token(
    *,
    github_username: str = "testuser",
    instance_id: str = "test-instance-123",
    challenge_type: str = "devops-lab-azure",
    challenges: int | None = None,
    timestamp: float | None = None,
) -> str:
    if timestamp is None:
        timestamp = datetime.now(UTC).timestamp()

    if challenges is None:
        challenges = REQUIRED_CHALLENGES_BY_TYPE.get(challenge_type, 7)

    payload = {
        "github_username": github_username,
        "instance_id": instance_id,
        "challenges": challenges,
        "challenge": challenge_type,
        "timestamp": timestamp,
        "date": "2026-02-13",
        "time": "10:45:00",
    }

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
class TestVerifyIacToken:
    """Tests for verify_iac_token."""

    def test_valid_azure_token_succeeds(self):
        token = _create_token(challenge_type="devops-lab-azure")
        result = verify_iac_token(token, "testuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.challenge_type == "devops-lab-azure"
        assert (
            result.challenges_completed
            == REQUIRED_CHALLENGES_BY_TYPE["devops-lab-azure"]
        )

    @pytest.mark.parametrize(
        "challenge_type",
        ["devops-lab-aws", "devops-lab-gcp"],
    )
    def test_aws_gcp_tokens_succeed(self, challenge_type: str):
        token = _create_token(challenge_type=challenge_type)
        result = verify_iac_token(token, "testuser")

        assert result.is_valid is True
        assert "Congratulations" in result.message
        assert result.challenge_type == challenge_type

    @pytest.mark.parametrize(
        "challenge_type",
        ["devops-lab-azure", "devops-lab-aws", "devops-lab-gcp"],
    )
    def test_incomplete_challenges_fail_for_each_provider(self, challenge_type: str):
        token = _create_token(challenge_type=challenge_type, challenges=3)
        result = verify_iac_token(token, "testuser")

        assert result.is_valid is False
        assert "Incomplete incidents" in result.message

    def test_invalid_base64_fails(self):
        result = verify_iac_token("not-base64", "testuser")
        assert result.is_valid is False
        assert "Invalid token format" in result.message

    def test_invalid_challenge_type_fails(self):
        token = _create_token(challenge_type="some-other-lab")
        result = verify_iac_token(token, "testuser")

        assert result.is_valid is False
        assert "Invalid challenge type" in result.message

    def test_username_mismatch_fails(self):
        token = _create_token(github_username="differentuser")
        result = verify_iac_token(token, "testuser")

        assert result.is_valid is False
        assert "username mismatch" in result.message.lower()

    def test_invalid_signature_fails(self):
        token = _create_token(challenge_type="devops-lab-azure")
        token_data = json.loads(base64.b64decode(token))
        token_data["signature"] = "tampered" + token_data["signature"][8:]
        tampered_token = base64.b64encode(json.dumps(token_data).encode()).decode()

        result = verify_iac_token(tampered_token, "testuser")
        assert result.is_valid is False
        assert "Invalid token signature" in result.message

    def test_future_timestamp_fails(self):
        token = _create_token(
            challenge_type="devops-lab-azure",
            timestamp=datetime.now(UTC).timestamp() + 7200,
        )
        result = verify_iac_token(token, "testuser")

        assert result.is_valid is False
        assert "future" in result.message.lower()

    def test_accepted_challenge_types_include_all_three_providers(self):
        assert ACCEPTED_CHALLENGE_TYPES == {
            "devops-lab-azure",
            "devops-lab-aws",
            "devops-lab-gcp",
        }
