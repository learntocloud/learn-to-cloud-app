"""Unit tests for verification.requirements.

Tests cover:
- get_prerequisite_phase returns correct gating rules
- RequirementIndex.from_phases builds the expected lookups
- Async convenience helpers (get_requirement_by_id, etc.) delegate via the index
- is_phase_verification_locked prerequisite checking
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    Phase,
    PhaseHandsOnVerificationOverview,
)
from learn_to_cloud_shared.verification.requirements import (
    RequirementIndex,
    get_phase_id_for_requirement,
    get_prerequisite_phase,
    get_requirement_by_id,
    get_requirement_ids_for_phase,
    get_requirements_for_phase,
    is_phase_verification_locked,
)


def _make_requirement(req_id: str = "req-1") -> HandsOnRequirement:
    from learn_to_cloud_shared.testing.requirement_factories import (
        journal_api_verifier_requirement,
    )

    return journal_api_verifier_requirement(
        id=req_id,
        name="Test Requirement",
        description="Test",
    )


def _make_phase_with_requirements(phase_id: int, req_ids: list[str]) -> Phase:
    reqs = [_make_requirement(rid) for rid in req_ids]
    return Phase(
        uuid=uuid4(),
        id=phase_id,
        name=f"Phase {phase_id}",
        slug=f"phase{phase_id}",
        order=phase_id,
        topics=[],
        hands_on_verification=PhaseHandsOnVerificationOverview(requirements=reqs),
    )


# ---------------------------------------------------------------------------
# get_prerequisite_phase (pure lookup -- no mocking)
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
# RequirementIndex.from_phases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequirementIndex:
    def test_from_phases_builds_lookups(self):
        phase3 = _make_phase_with_requirements(3, ["req-a", "req-b"])
        phase4 = _make_phase_with_requirements(4, ["req-c"])

        index = RequirementIndex.from_phases([phase3, phase4])

        assert sorted(index.by_phase.keys()) == [3, 4]
        assert {r.id for r in index.by_phase[3]} == {"req-a", "req-b"}
        assert set(index.by_id.keys()) == {"req-a", "req-b", "req-c"}
        assert index.phase_id_by_req_id["req-a"] == 3
        assert index.phase_id_by_req_id["req-c"] == 4

    def test_from_phases_handles_no_verification(self):
        phase = Phase(
            uuid=uuid4(),
            id=0,
            name="P0",
            slug="phase0",
            order=0,
            topics=[],
            hands_on_verification=None,
        )

        index = RequirementIndex.from_phases([phase])

        assert index.by_phase[0] == []
        assert index.by_id == {}
        assert index.phase_id_by_req_id == {}

    def test_requirements_for_phase_returns_empty_for_unknown(self):
        index = RequirementIndex()
        assert index.requirements_for_phase(99) == []
        assert index.requirement_ids_for_phase(99) == []


# ---------------------------------------------------------------------------
# Async lookup helpers (delegate to load_requirement_index)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAsyncRequirementLookups:
    @pytest.mark.asyncio
    async def test_get_requirements_for_known_phase(self):
        phase = _make_phase_with_requirements(3, ["req-a", "req-b"])
        with patch(
            "learn_to_cloud_shared.verification.requirements.get_all_phases",
            new_callable=AsyncMock,
            return_value=(phase,),
        ):
            reqs = await get_requirements_for_phase(AsyncMock(), 3)
        assert len(reqs) == 2

    @pytest.mark.asyncio
    async def test_get_requirements_for_unknown_phase(self):
        with patch(
            "learn_to_cloud_shared.verification.requirements.get_all_phases",
            new_callable=AsyncMock,
            return_value=(),
        ):
            reqs = await get_requirements_for_phase(AsyncMock(), 99)
        assert reqs == []

    @pytest.mark.asyncio
    async def test_get_requirement_by_id_found(self):
        phase = _make_phase_with_requirements(3, ["req-a"])
        with patch(
            "learn_to_cloud_shared.verification.requirements.get_all_phases",
            new_callable=AsyncMock,
            return_value=(phase,),
        ):
            req = await get_requirement_by_id(AsyncMock(), "req-a")
        assert req is not None
        assert req.id == "req-a"

    @pytest.mark.asyncio
    async def test_get_requirement_by_id_not_found(self):
        with patch(
            "learn_to_cloud_shared.verification.requirements.get_all_phases",
            new_callable=AsyncMock,
            return_value=(),
        ):
            assert await get_requirement_by_id(AsyncMock(), "nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_phase_id_for_requirement(self):
        phase = _make_phase_with_requirements(3, ["req-a"])
        with patch(
            "learn_to_cloud_shared.verification.requirements.get_all_phases",
            new_callable=AsyncMock,
            return_value=(phase,),
        ):
            assert await get_phase_id_for_requirement(AsyncMock(), "req-a") == 3

    @pytest.mark.asyncio
    async def test_get_requirement_ids_for_phase(self):
        phase = _make_phase_with_requirements(3, ["req-a", "req-b"])
        with patch(
            "learn_to_cloud_shared.verification.requirements.get_all_phases",
            new_callable=AsyncMock,
            return_value=(phase,),
        ):
            ids = await get_requirement_ids_for_phase(AsyncMock(), 3)
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
                "learn_to_cloud_shared.verification.requirements.get_all_phases",
                new_callable=AsyncMock,
                return_value=(phase3, phase4),
            ),
            patch(
                "learn_to_cloud_shared.verification.requirements.SubmissionRepository",
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
                "learn_to_cloud_shared.verification.requirements.get_all_phases",
                new_callable=AsyncMock,
                return_value=(phase3, phase4),
            ),
            patch(
                "learn_to_cloud_shared.verification.requirements.SubmissionRepository",
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
