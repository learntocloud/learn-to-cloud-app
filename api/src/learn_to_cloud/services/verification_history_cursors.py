"""Opaque cursors for verification-attempt history."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from itsdangerous import BadData, URLSafeSerializer
from learn_to_cloud_shared.core.config import get_web_settings

_CURSOR_SALT = "verification-history-v1"


class VerificationHistoryCursorError(Exception):
    """Raised when a history cursor is invalid or belongs to another scope."""


@dataclass(frozen=True, slots=True)
class VerificationHistoryCursor:
    created_at: datetime
    attempt_id: UUID


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(
        get_web_settings().session.secret_key,
        salt=_CURSOR_SALT,
    )


def create_history_cursor(
    *,
    user_id: int,
    requirement_uuid: UUID,
    created_at: datetime,
    attempt_id: UUID,
) -> str:
    return _serializer().dumps(
        {
            "user_id": user_id,
            "requirement_uuid": str(requirement_uuid),
            "created_at": created_at.isoformat(),
            "attempt_id": str(attempt_id),
        }
    )


def load_history_cursor(
    token: str,
    *,
    expected_user_id: int,
    expected_requirement_uuid: UUID,
) -> VerificationHistoryCursor:
    try:
        payload = _serializer().loads(token)
    except BadData as exc:
        raise VerificationHistoryCursorError("Invalid history cursor.") from exc
    if not isinstance(payload, dict):
        raise VerificationHistoryCursorError("Invalid history cursor.")

    user_id = _expect_int(payload, "user_id")
    requirement_uuid = _expect_uuid(payload, "requirement_uuid")
    if user_id != expected_user_id or requirement_uuid != expected_requirement_uuid:
        raise VerificationHistoryCursorError("History cursor scope mismatch.")

    created_at_raw = _expect_str(payload, "created_at")
    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError as exc:
        raise VerificationHistoryCursorError("Invalid history cursor date.") from exc
    if created_at.tzinfo is None:
        raise VerificationHistoryCursorError("Invalid history cursor date.")

    return VerificationHistoryCursor(
        created_at=created_at,
        attempt_id=_expect_uuid(payload, "attempt_id"),
    )


def _expect_str(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise VerificationHistoryCursorError(f"History cursor is missing {field_name}.")
    return value


def _expect_int(payload: dict[Any, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise VerificationHistoryCursorError(f"History cursor is missing {field_name}.")
    return value


def _expect_uuid(payload: dict[Any, Any], field_name: str) -> UUID:
    try:
        return UUID(_expect_str(payload, field_name))
    except ValueError as exc:
        raise VerificationHistoryCursorError(
            f"History cursor has invalid {field_name}."
        ) from exc
