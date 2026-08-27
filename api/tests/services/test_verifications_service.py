"""Focused tests for dedicated verification page contexts."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptCardProjection,
    AttemptHistoryProjection,
)

from learn_to_cloud.services.verifications_service import (
    _history_item,
    _safe_artifact_url,
    get_phase_verification_context,
)


def _terminal(requirement_uuid: UUID, *, outcome: str) -> AttemptCardProjection:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    return AttemptCardProjection(
        id=uuid4(),
        requirement_uuid=requirement_uuid,
        submission_value_kind="github_url",
        submitted_value="https://github.com/learner/project",
        github_username_snapshot="learner",
        cloud_provider=None,
        outcome=outcome,
        feedback_json=None,
        validation_message="Needs work" if outcome == "failed" else None,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.unit
async def test_phase_context_keeps_only_first_incomplete_requirement_actionable():
    passed = SimpleNamespace(
        uuid=uuid4(),
        slug="passed",
        name="Passed",
        description="",
        submission_type="ctf_token",
        type_config=SimpleNamespace(placeholder=None),
    )
    current = SimpleNamespace(
        uuid=uuid4(),
        slug="current",
        name="Current",
        description="",
        submission_type="ctf_token",
        type_config=SimpleNamespace(placeholder=None),
    )
    upcoming = SimpleNamespace(
        uuid=uuid4(),
        slug="upcoming",
        name="Upcoming",
        description="",
        submission_type="ctf_token",
        type_config=SimpleNamespace(placeholder=None),
    )
    phase = SimpleNamespace(
        order=2,
        hands_on_verification=SimpleNamespace(requirements=[passed, current, upcoming]),
    )
    repository = MagicMock()
    repository.get_latest_terminal_for_requirements = AsyncMock(
        return_value=[_terminal(passed.uuid, outcome="succeeded")]
    )
    repository.get_active_for_requirements = AsyncMock(return_value=[])
    repository.get_terminal_history_for_requirements = AsyncMock(return_value=[])

    with (
        patch(
            "learn_to_cloud.services.verifications_service.get_phase_by_slug",
            return_value=phase,
        ),
        patch(
            "learn_to_cloud.services.verifications_service.fetch_phase_progress",
            return_value=MagicMock(),
        ),
        patch(
            "learn_to_cloud.services.verifications_service."
            "is_phase_verification_locked",
            return_value=(False, None),
        ),
        patch(
            "learn_to_cloud.services.verifications_service."
            "VerificationAttemptRepository",
            return_value=repository,
        ),
    ):
        context = await get_phase_verification_context(
            AsyncMock(), 7, 2, github_username="learner"
        )

    assert context is not None
    assert [item.page_state for item in context.requirements] == [
        "passed",
        "current",
        "up_next",
    ]


@pytest.mark.unit
def test_history_artifact_only_exposes_valid_url_value_kinds():
    assert (
        _safe_artifact_url("github_url", "https://github.com/learner/project")
        == "https://github.com/learner/project"
    )
    assert _safe_artifact_url("token", "secret-token") is None
    assert _safe_artifact_url("text", "https://example.com/reflection") is None
    assert _safe_artifact_url("deployed_url", "javascript:alert(1)") is None


@pytest.mark.unit
def test_history_context_never_contains_token_or_reflection_values():
    row = AttemptHistoryProjection(
        id=uuid4(),
        requirement_uuid=uuid4(),
        submission_value_kind="token",
        submitted_value="secret-token",
        outcome="failed",
        feedback_json=None,
        validation_message="Invalid token",
        completed_at=None,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    item = _history_item(row)
    assert item.artifact_url is None
    assert not hasattr(item, "submitted_value")
