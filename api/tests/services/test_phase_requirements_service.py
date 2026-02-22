"""Unit tests for phase_requirements_service.

Tests cover:
- get_prerequisite_phase returns correct gating rules
- get_requirements_for_phase returns requirements or empty list
- get_requirement_by_id / get_phase_id_for_requirement lookups
- is_phase_verification_locked prerequisite checking
"""

from unittest.mock import AsyncMock, patch

import pytest

from models import SubmissionType
from schemas import (
    HandsOnRequirement,
    Phase,
    PhaseHandsOnVerificationOverview,
)
from services.phase_requirements_service import (
    _get_requirement_id_map,
    _get_requirement_phase_id_map,
    _get_requirements_map,
    get_phase_id_for_requirement,
    get_prerequisite_phase,
    get_requirement_by_id,
    get_requirement_ids_for_phase,
    get_requirements_for_phase,
    is_phase_verification_locked,
)


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """Clear lru_cache between tests."""
    yield
    _get_requirements_map.cache_clear()
    _get_requirement_id_map.cache_clear()
    _get_requirement_phase_id_map.cache_clear()


def _make_requirement(req_id: str = "req-1") -> HandsOnRequirement:
    return HandsOnRequirement(
        id=req_id,
        submission_type=SubmissionType.CODE_ANALYSIS,
        name="Test Requirement",
        description="Test",
    )


def _make_phase_with_requirements(phase_id: int, req_ids: list[str]) -> Phase:
    reqs = [_make_requirement(rid) for rid in req_ids]
    return Phase(
        id=phase_id,
        name=f"Phase {phase_id}",
        slug=f"phase{phase_id}",
        order=phase_id,
        topics=[],
        hands_on_verification=PhaseHandsOnVerificationOverview(requirements=reqs),
    )


# ---------------------------------------------------------------------------
# get_prerequisite_phase (pure lookup — no mocking)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPrerequisitePhase:
    def test_phase_4_requires_3(self):
        assert get_prerequisite_phase(4) == 3

    def test_phase_5_requires_4(self):
        assert get_prerequisite_phase(5) == 4

    def test_phase_6_requires_5(self):
        assert get_prerequisite_phase(6) == 5

    def test_phase_0_has_no_prerequisite(self):
        assert get_prerequisite_phase(0) is None

    def test_phase_3_has_no_prerequisite(self):
        assert get_prerequisite_phase(3) is None

    def test_unknown_phase_has_no_prerequisite(self):
        assert get_prerequisite_phase(99) is None


# ---------------------------------------------------------------------------
# Requirement lookup functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequirementLookups:
    def test_get_requirements_for_known_phase(self):
        phase = _make_phase_with_requirements(3, ["req-a", "req-b"])
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(phase,),
        ):
            reqs = get_requirements_for_phase(3)
        assert len(reqs) == 2

    def test_get_requirements_for_unknown_phase(self):
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(),
        ):
            reqs = get_requirements_for_phase(99)
        assert reqs == []

    def test_get_requirement_by_id_found(self):
        phase = _make_phase_with_requirements(3, ["req-a"])
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(phase,),
        ):
            req = get_requirement_by_id("req-a")
        assert req is not None
        assert req.id == "req-a"

    def test_get_requirement_by_id_not_found(self):
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(),
        ):
            assert get_requirement_by_id("nonexistent") is None

    def test_get_phase_id_for_requirement(self):
        phase = _make_phase_with_requirements(3, ["req-a"])
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(phase,),
        ):
            assert get_phase_id_for_requirement("req-a") == 3

    def test_get_requirement_ids_for_phase(self):
        phase = _make_phase_with_requirements(3, ["req-a", "req-b"])
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(phase,),
        ):
            ids = get_requirement_ids_for_phase(3)
        assert ids == ["req-a", "req-b"]


# ---------------------------------------------------------------------------
# is_phase_verification_locked
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsPhaseVerificationLocked:
    @pytest.mark.asyncio
    async def test_no_prerequisite_is_unlocked(self):
        is_locked, prereq = await is_phase_verification_locked(
            AsyncMock(), user_id=1, phase_id=0
        )
        assert is_locked is False
        assert prereq is None

    @pytest.mark.asyncio
    async def test_locked_when_prerequisite_incomplete(self):
        phase3 = _make_phase_with_requirements(3, ["p3-req"])
        phase4 = _make_phase_with_requirements(4, ["p4-req"])

        with (
            patch(
                "services.content_service.get_all_phases",
                autospec=True,
                return_value=(phase3, phase4),
            ),
            patch(
                "repositories.submission_repository.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
            MockRepo.return_value.are_all_requirements_validated = AsyncMock(
                return_value=False
            )
            is_locked, prereq = await is_phase_verification_locked(
                AsyncMock(), user_id=1, phase_id=4
            )

        assert is_locked is True
        assert prereq == 3

    @pytest.mark.asyncio
    async def test_unlocked_when_prerequisite_complete(self):
        phase3 = _make_phase_with_requirements(3, ["p3-req"])
        phase4 = _make_phase_with_requirements(4, ["p4-req"])

        with (
            patch(
                "services.content_service.get_all_phases",
                autospec=True,
                return_value=(phase3, phase4),
            ),
            patch(
                "repositories.submission_repository.SubmissionRepository",
                autospec=True,
            ) as MockRepo,
        ):
            MockRepo.return_value.are_all_requirements_validated = AsyncMock(
                return_value=True
            )
            is_locked, prereq = await is_phase_verification_locked(
                AsyncMock(), user_id=1, phase_id=4
            )

        assert is_locked is False
        assert prereq is None
