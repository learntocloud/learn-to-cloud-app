"""Unit tests for signed verification status tokens."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from learn_to_cloud.services.verification_status_tokens import (
    VerificationStatusTokenError,
    create_verification_status_token,
    load_verification_status_token,
)

pytestmark = pytest.mark.unit


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        session_secret_key="test-status-token-secret",
        verification_wait_timeout=60,
    )


def test_token_round_trip_validates_expected_user():
    job_id = uuid4()
    instance_id = str(job_id)

    with patch(
        "learn_to_cloud.services.verification_status_tokens.get_settings",
        return_value=_settings(),
    ):
        token = create_verification_status_token(
            user_id=42,
            job_id=job_id,
            instance_id=instance_id,
            requirement_id="journal-api",
        )
        result = load_verification_status_token(token, expected_user_id=42)

    assert result.user_id == 42
    assert result.job_id == str(job_id)
    assert result.instance_id == instance_id
    assert result.requirement_id == "journal-api"


def test_tampered_token_is_rejected():
    with (
        patch(
            "learn_to_cloud.services.verification_status_tokens.get_settings",
            return_value=_settings(),
        ),
        pytest.raises(VerificationStatusTokenError, match="invalid"),
    ):
        load_verification_status_token("not-a-valid-token", expected_user_id=42)


def test_user_mismatch_is_rejected():
    with (
        patch(
            "learn_to_cloud.services.verification_status_tokens.get_settings",
            return_value=_settings(),
        ),
        pytest.raises(VerificationStatusTokenError, match="user mismatch"),
    ):
        token = create_verification_status_token(
            user_id=42,
            job_id=uuid4(),
            instance_id=str(uuid4()),
            requirement_id="journal-api",
        )
        load_verification_status_token(token, expected_user_id=7)


def test_invalid_uuid_fields_are_rejected():
    with (
        patch(
            "learn_to_cloud.services.verification_status_tokens.get_settings",
            return_value=_settings(),
        ),
        pytest.raises(VerificationStatusTokenError, match="invalid instance_id"),
    ):
        token = create_verification_status_token(
            user_id=42,
            job_id=uuid4(),
            instance_id="not-a-uuid",
            requirement_id="journal-api",
        )
        load_verification_status_token(token, expected_user_id=42)


def test_expired_token_is_rejected():
    settings = _settings()
    settings.verification_wait_timeout = -121

    with (
        patch(
            "learn_to_cloud.services.verification_status_tokens.get_settings",
            return_value=settings,
        ),
        pytest.raises(VerificationStatusTokenError, match="expired"),
    ):
        token = create_verification_status_token(
            user_id=42,
            job_id=uuid4(),
            instance_id=str(uuid4()),
            requirement_id="journal-api",
        )
        load_verification_status_token(token, expected_user_id=42)
