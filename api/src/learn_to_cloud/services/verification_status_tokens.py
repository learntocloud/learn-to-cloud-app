"""Signed tokens for browser-visible verification status polling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from learn_to_cloud_shared.core.config import get_settings

_TOKEN_SALT = "verification-status-v1"


class VerificationStatusTokenError(Exception):
    """Raised when a verification status token is invalid."""


@dataclass(frozen=True, slots=True)
class VerificationStatusToken:
    user_id: int
    job_id: str
    instance_id: str
    requirement_id: str


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret_key, salt=_TOKEN_SALT)


def create_verification_status_token(
    *,
    user_id: int,
    job_id: UUID,
    instance_id: str,
    requirement_id: str,
) -> str:
    payload = {
        "user_id": user_id,
        "job_id": str(job_id),
        "instance_id": instance_id,
        "requirement_id": requirement_id,
    }
    return _serializer().dumps(payload)


def load_verification_status_token(
    token: str,
    *,
    expected_user_id: int,
) -> VerificationStatusToken:
    max_age = get_settings().verification_wait_timeout + 120
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise VerificationStatusTokenError(
            "Verification status token expired."
        ) from exc
    except BadData as exc:
        raise VerificationStatusTokenError(
            "Verification status token is invalid."
        ) from exc

    if not isinstance(payload, dict):
        raise VerificationStatusTokenError(
            "Verification status token payload is invalid."
        )

    user_id = _expect_int(payload, "user_id")
    if user_id != expected_user_id:
        raise VerificationStatusTokenError("Verification status token user mismatch.")

    return VerificationStatusToken(
        user_id=user_id,
        job_id=_expect_uuid_str(payload, "job_id"),
        instance_id=_expect_uuid_str(payload, "instance_id"),
        requirement_id=_expect_str(payload, "requirement_id"),
    )


def _expect_str(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise VerificationStatusTokenError(
            f"Verification status token missing {field_name}."
        )
    return value


def _expect_int(payload: dict[Any, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise VerificationStatusTokenError(
            f"Verification status token missing {field_name}."
        )
    return value


def _expect_uuid_str(payload: dict[Any, Any], field_name: str) -> str:
    value = _expect_str(payload, field_name)
    try:
        UUID(value)
    except ValueError as exc:
        raise VerificationStatusTokenError(
            f"Verification status token has invalid {field_name}."
        ) from exc
    return value
