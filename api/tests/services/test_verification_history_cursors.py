"""Tests for scoped opaque verification-history cursors."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from itsdangerous import URLSafeSerializer

from learn_to_cloud.services.verification_history_cursors import (
    VerificationHistoryCursorError,
    create_history_cursor,
    load_history_cursor,
)


@pytest.fixture
def cursor_serializer():
    with patch(
        "learn_to_cloud.services.verification_history_cursors._serializer",
        return_value=URLSafeSerializer("test-secret", salt="history"),
    ):
        yield


@pytest.mark.unit
def test_cursor_round_trip_preserves_equal_timestamp_tiebreaker(cursor_serializer):
    requirement_uuid = uuid4()
    attempt_id = uuid4()
    created_at = datetime(2026, 8, 1, 12, 30, tzinfo=UTC)
    token = create_history_cursor(
        user_id=7,
        requirement_uuid=requirement_uuid,
        created_at=created_at,
        attempt_id=attempt_id,
    )

    cursor = load_history_cursor(
        token,
        expected_user_id=7,
        expected_requirement_uuid=requirement_uuid,
    )

    assert cursor.created_at == created_at
    assert cursor.attempt_id == attempt_id
    assert str(attempt_id) not in token


@pytest.mark.unit
def test_cursor_cannot_cross_users(cursor_serializer):
    requirement_uuid = uuid4()
    token = create_history_cursor(
        user_id=7,
        requirement_uuid=requirement_uuid,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        attempt_id=uuid4(),
    )

    with pytest.raises(VerificationHistoryCursorError):
        load_history_cursor(
            token,
            expected_user_id=8,
            expected_requirement_uuid=requirement_uuid,
        )
