"""Tests for verification workspace view data."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptHistoryProjection,
)
from learn_to_cloud_shared.schemas import (
    LearningProgress,
    Phase,
    PhaseHandsOnVerificationOverview,
    PhaseOverview,
    PhaseProgress,
    PhaseSubmissionContext,
    UserProgress,
    VerificationProgress,
)
from learn_to_cloud_shared.testing.requirement_factories import (
    career_reflection_requirement,
    repo_fork_requirement,
)

from learn_to_cloud.rendering.context import CheckingCardContext
from learn_to_cloud.services.verification_page_service import (
    get_phase_verification_workspace,
    get_verifications_overview,
)


def _phase_overview(order: int) -> PhaseOverview:
    return PhaseOverview(
        uuid=uuid4(),
        order=order,
        name=f"Phase {order}",
        slug=f"phase{order}",
    )


def _phase_progress(
    order: int,
    *,
    verified: int,
    required: int,
) -> PhaseProgress:
    return PhaseProgress(
        phase_id=order,
        learning=LearningProgress(steps_completed=0, steps_required=1),
        verification=VerificationProgress(
            requirements_verified=verified,
            requirements_required=required,
        ),
    )


@pytest.mark.unit
async def test_overview_builds_progress_gating_and_next_phase():
    phases = tuple(_phase_overview(order) for order in (2, 3, 4, 5))
    user_progress = UserProgress(
        user_id=42,
        phases={
            2: _phase_progress(2, verified=0, required=0),
            3: _phase_progress(3, verified=1, required=1),
            4: _phase_progress(4, verified=1, required=2),
            5: _phase_progress(5, verified=0, required=1),
        },
        total_phases=4,
    )

    with (
        patch(
            "learn_to_cloud.services.verification_page_service.get_curriculum_overview",
            return_value=phases,
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.fetch_user_progress",
            new=AsyncMock(return_value=user_progress),
        ),
    ):
        result = await get_verifications_overview(AsyncMock(), user_id=42)

    assert [item.phase.order for item in result.phases] == [3, 4, 5]
    assert result.requirements_verified == 2
    assert result.requirements_required == 4
    assert result.percentage == 50.0
    assert result.next_phase is result.phases[1]
    assert result.phases[1].status == "in_progress"
    assert result.phases[2].is_locked is True
    assert result.phases[2].prerequisite_phase_id == 4
    assert result.phases[2].status == "locked"


@pytest.mark.unit
async def test_overview_has_no_next_phase_when_everything_is_verified():
    phases = (_phase_overview(3),)
    user_progress = UserProgress(
        user_id=42,
        phases={3: _phase_progress(3, verified=1, required=1)},
        total_phases=1,
    )

    with (
        patch(
            "learn_to_cloud.services.verification_page_service.get_curriculum_overview",
            return_value=phases,
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.fetch_user_progress",
            new=AsyncMock(return_value=user_progress),
        ),
    ):
        result = await get_verifications_overview(AsyncMock(), user_id=42)

    assert result.next_phase is None
    assert result.is_complete is True
    assert result.percentage == 100.0


@pytest.mark.unit
async def test_phase_workspace_preserves_active_attempt_polling_state():
    requirement = repo_fork_requirement(slug="verify-repository")
    phase = Phase(
        uuid=uuid4(),
        order=4,
        name="Deploy",
        slug="phase4",
        hands_on_verification=PhaseHandsOnVerificationOverview(
            requirements=[requirement]
        ),
    )
    progress = _phase_progress(4, verified=0, required=1)
    active_attempt = SimpleNamespace(
        id=uuid4(),
        requirement_uuid=requirement.uuid,
    )
    repository = MagicMock(
        get_active_for_requirements=AsyncMock(return_value=[active_attempt]),
        list_terminal_history_for_requirements=AsyncMock(return_value=[]),
    )

    with (
        patch(
            "learn_to_cloud.services.verification_page_service.fetch_phase_progress",
            new=AsyncMock(return_value=progress),
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.get_phase_submission_context",
            new=AsyncMock(
                return_value=PhaseSubmissionContext(
                    submissions_by_req={},
                    feedback_by_req={},
                )
            ),
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.VerificationAttemptRepository",
            return_value=repository,
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.create_verification_status_token",
            return_value="status-token",
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.is_phase_verification_locked",
            new=AsyncMock(return_value=(True, 3)),
        ),
    ):
        result = await get_phase_verification_workspace(
            AsyncMock(),
            user_id=42,
            phase=phase,
            github_username="learner",
        )

    card = result.card_contexts_by_req[requirement.slug]
    assert result.phase_progress is progress
    assert result.verification_locked is True
    assert result.prerequisite_phase_id == 3
    assert isinstance(card, CheckingCardContext)
    assert card.kind == "checking"
    assert card.verification_status_token == "status-token"
    repository.get_active_for_requirements.assert_awaited_once_with(
        42, {requirement.uuid: requirement}
    )
    repository.list_terminal_history_for_requirements.assert_awaited_once_with(
        42,
        {requirement.uuid: requirement},
        limit=11,
        offset=0,
    )


@pytest.mark.unit
async def test_phase_workspace_maps_safe_history_and_suppresses_reflection_feedback():
    repository_requirement = repo_fork_requirement(slug="verify-repository")
    reflection_requirement = career_reflection_requirement(slug="career-reflection")
    phase = Phase(
        uuid=uuid4(),
        order=7,
        name="Career",
        slug="phase7",
        hands_on_verification=PhaseHandsOnVerificationOverview(
            requirements=[repository_requirement, reflection_requirement]
        ),
    )
    progress = _phase_progress(7, verified=0, required=2)
    completed_at = datetime.now(UTC)
    repository_attempt = AttemptHistoryProjection(
        id=uuid4(),
        requirement_uuid=repository_requirement.uuid,
        outcome="failed",
        feedback_json=[
            {
                "task_name": "Repository",
                "passed": False,
                "feedback": "Add the required file.",
                "next_steps": "Commit the file and retry.",
            }
        ],
        validation_message="Repository evidence is incomplete.",
        completed_at=completed_at,
    )
    reflection_attempt = AttemptHistoryProjection(
        id=uuid4(),
        requirement_uuid=reflection_requirement.uuid,
        outcome="succeeded",
        feedback_json=[
            {
                "task_name": "Private reflection",
                "passed": True,
                "feedback": "Sensitive retained coaching.",
                "next_steps": "",
            }
        ],
        validation_message=None,
        completed_at=completed_at,
    )
    history_rows = [repository_attempt, reflection_attempt]
    history_rows.extend([repository_attempt] * 9)
    repository = MagicMock(
        get_active_for_requirements=AsyncMock(return_value=[]),
        list_terminal_history_for_requirements=AsyncMock(return_value=history_rows),
    )

    with (
        patch(
            "learn_to_cloud.services.verification_page_service.fetch_phase_progress",
            new=AsyncMock(return_value=progress),
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.get_phase_submission_context",
            new=AsyncMock(
                return_value=PhaseSubmissionContext(
                    submissions_by_req={},
                    feedback_by_req={},
                )
            ),
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.VerificationAttemptRepository",
            return_value=repository,
        ),
        patch(
            "learn_to_cloud.services.verification_page_service.is_phase_verification_locked",
            new=AsyncMock(return_value=(False, None)),
        ),
    ):
        result = await get_phase_verification_workspace(
            AsyncMock(),
            user_id=42,
            phase=phase,
            github_username="learner",
            history_page=2,
        )

    assert result.history.page == 2
    assert result.history.has_previous is True
    assert result.history.has_next is True
    assert len(result.history.items) == 10
    first = result.history.items[0]
    assert first.status_label == "Needs work"
    assert first.status_variant == "error"
    assert first.feedback_tasks[0]["message"] == "Add the required file."
    assert first.completed_at == completed_at
    reflection = result.history.items[1]
    assert reflection.feedback_tasks == []
    assert reflection.feedback_passed == 0
    repository.list_terminal_history_for_requirements.assert_awaited_once_with(
        42,
        {
            repository_requirement.uuid: repository_requirement,
            reflection_requirement.uuid: reflection_requirement,
        },
        limit=11,
        offset=10,
    )
