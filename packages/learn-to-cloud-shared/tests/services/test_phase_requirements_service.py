"""Unit tests for the requirements lookup helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from learn_to_cloud_shared.requirements import (
    RequirementIndex,
    get_prerequisite_phase,
    get_requirement_by_slug,
    is_phase_verification_locked,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement
from learn_to_cloud_shared.testing.requirement_factories import (
    journal_api_verifier_requirement,
)


def _make_requirement(slug: str = "req-1") -> HandsOnRequirement:
    return journal_api_verifier_requirement(
        slug=slug,
        name="Test Requirement",
        description="Test",
    )


def _make_requirements_by_phase_order(
    order: int, slugs: list[str]
) -> dict[int, list[HandsOnRequirement]]:
    return {order: [_make_requirement(s) for s in slugs]}


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


@pytest.mark.unit
class TestRequirementIndex:
    def test_from_requirements_by_phase_order_builds_lookups(self):
        by_phase_order = _make_requirements_by_phase_order(3, ["req-a", "req-b"])
        by_phase_order.update(_make_requirements_by_phase_order(4, ["req-c"]))

        index = RequirementIndex.from_requirements_by_phase_order(by_phase_order)

        assert sorted(index.by_phase_order.keys()) == [3, 4]
        assert {r.slug for r in index.by_phase_order[3]} == {"req-a", "req-b"}
        assert set(index.by_slug.keys()) == {"req-a", "req-b", "req-c"}
        assert index.phase_order_by_req_slug["req-a"] == 3
        assert index.phase_order_by_req_slug["req-c"] == 4

    def test_from_requirements_by_phase_order_handles_empty(self):
        index = RequirementIndex.from_requirements_by_phase_order({0: []})

        assert index.by_phase_order[0] == []
        assert index.by_slug == {}
        assert index.phase_order_by_req_slug == {}

    def test_requirements_for_phase_returns_empty_for_unknown(self):
        index = RequirementIndex()
        assert index.requirements_for_phase(99) == []
        assert index.requirement_slugs_for_phase(99) == []


@pytest.mark.unit
class TestSyncRequirementLookups:
    def test_get_requirement_by_slug_found(self):
        by_phase_order = _make_requirements_by_phase_order(3, ["req-a"])
        with patch(
            "learn_to_cloud_shared.requirements.get_requirements_by_phase_order",
            return_value=by_phase_order,
        ):
            req = get_requirement_by_slug("req-a")
        assert req is not None
        assert req.slug == "req-a"

    def test_get_requirement_by_slug_not_found(self):
        with patch(
            "learn_to_cloud_shared.requirements.get_requirements_by_phase_order",
            return_value={},
        ):
            assert get_requirement_by_slug("nonexistent") is None


@pytest.mark.unit
class TestIsPhaseVerificationLocked:
    @pytest.mark.asyncio
    async def test_no_prerequisite_is_unlocked(self):
        is_locked, prereq = await is_phase_verification_locked(
            AsyncMock(), user_id=1, phase_order=0
        )
        assert is_locked is False
        assert prereq is None

    @pytest.mark.asyncio
    async def test_locked_when_prerequisite_incomplete(self):
        by_phase_order = _make_requirements_by_phase_order(3, ["p3-req"])
        by_phase_order.update(_make_requirements_by_phase_order(4, ["p4-req"]))

        with (
            patch(
                "learn_to_cloud_shared.requirements.get_requirements_by_phase_order",
                return_value=by_phase_order,
            ),
            patch(
                "learn_to_cloud_shared.requirements.are_all_requirements_succeeded",
                new=AsyncMock(return_value=False),
            ),
        ):
            is_locked, prereq = await is_phase_verification_locked(
                AsyncMock(), user_id=1, phase_order=4
            )

        assert is_locked is True
        assert prereq == 3

    @pytest.mark.asyncio
    async def test_unlocked_when_prerequisite_complete(self):
        by_phase_order = _make_requirements_by_phase_order(3, ["p3-req"])
        by_phase_order.update(_make_requirements_by_phase_order(4, ["p4-req"]))

        with (
            patch(
                "learn_to_cloud_shared.requirements.get_requirements_by_phase_order",
                return_value=by_phase_order,
            ),
            patch(
                "learn_to_cloud_shared.requirements.are_all_requirements_succeeded",
                new=AsyncMock(return_value=True),
            ),
        ):
            is_locked, prereq = await is_phase_verification_locked(
                AsyncMock(), user_id=1, phase_order=4
            )

        assert is_locked is False
        assert prereq is None
