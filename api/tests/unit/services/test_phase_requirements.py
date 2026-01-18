"""Unit tests for services/phase_requirements.py.

Tests hands-on requirement configuration and helper functions.

Total test cases: 20
- TestPhaseRequirementsConstants: 5 tests
- TestHandsOnRequirements: 7 tests
- TestGetRequirementsForPhase: 4 tests
- TestGetRequirementById: 4 tests
"""

import pytest

from services.phase_requirements_service import (
    HANDS_ON_REQUIREMENTS,
    get_requirement_by_id,
    get_requirements_for_phase,
)


class TestPhaseRequirementsConstants:
    """Test phase requirements constants match spec.

    Per spec from api/docs/progression-system.md:
    - Phase 0: 15 steps, 12 questions, 1 hands-on
    - Phase 1: 36 steps, 12 questions, 3 hands-on
    - Phase 2: 30 steps, 12 questions, 2 hands-on
    - Phase 3: 31 steps, 8 questions, 1 hands-on
    - Phase 4: 51 steps, 18 questions, 1 hands-on
    - Phase 5: 55 steps, 12 questions, 4 hands-on
    - Phase 6: 64 steps, 12 questions, 1 hands-on
    """

    def test_seven_phases_exist(self):
        """Seven phases (0-6) have hands-on requirements defined."""
        assert len(HANDS_ON_REQUIREMENTS) == 7
        for phase_id in range(7):
            assert phase_id in HANDS_ON_REQUIREMENTS

    @pytest.mark.parametrize(
        "phase_id,expected_count",
        [
            (0, 1),
            (1, 3),
            (2, 2),
            (3, 1),
            (4, 1),
            (5, 4),
            (6, 1),
        ],
    )
    def test_phase_requirements_match_spec(self, phase_id, expected_count):
        """Each phase has correct number of hands-on requirements per spec."""
        requirements = HANDS_ON_REQUIREMENTS[phase_id]
        assert len(requirements) == expected_count

    def test_total_hands_on_requirements(self):
        """Total of 13 hands-on requirements across all phases."""
        total = sum(len(reqs) for reqs in HANDS_ON_REQUIREMENTS.values())
        assert total == 13

    def test_all_phases_are_sequential(self):
        """Phase IDs are sequential from 0 to 6."""
        phase_ids = sorted(HANDS_ON_REQUIREMENTS.keys())
        assert phase_ids == [0, 1, 2, 3, 4, 5, 6]

    def test_no_empty_phases(self):
        """No phase has zero hands-on requirements."""
        for phase_id, requirements in HANDS_ON_REQUIREMENTS.items():
            assert len(requirements) > 0, f"Phase {phase_id} has no requirements"


class TestHandsOnRequirements:
    """Test hands-on requirement data structure."""

    @pytest.mark.parametrize(
        "phase_id,expected_count",
        [
            (0, 1),
            (1, 3),
            (2, 2),
            (3, 1),
            (4, 1),
            (5, 4),
            (6, 1),
        ],
    )
    def test_hands_on_counts_match_spec(self, phase_id, expected_count):
        """Hands-on counts match spec for each phase."""
        requirements = get_requirements_for_phase(phase_id)
        assert len(requirements) == expected_count

    def test_all_phases_have_hands_on_definitions(self):
        """All 7 phases have hands-on requirement definitions."""
        for phase_id in range(7):
            requirements = get_requirements_for_phase(phase_id)
            assert requirements is not None
            assert isinstance(requirements, list)

    def test_all_requirements_have_unique_ids(self):
        """All hands-on requirement IDs are unique."""
        all_ids = []
        for requirements in HANDS_ON_REQUIREMENTS.values():
            for req in requirements:
                all_ids.append(req.id)

        assert len(all_ids) == len(set(all_ids)), "Duplicate requirement IDs found"

    def test_requirement_ids_match_phase(self):
        """Requirement IDs start with correct phase number."""
        for phase_id, requirements in HANDS_ON_REQUIREMENTS.items():
            for req in requirements:
                assert req.id.startswith(
                    f"phase{phase_id}-"
                ), f"Requirement {req.id} doesn't match phase {phase_id}"

    def test_all_requirements_have_submission_types(self):
        """All requirements have submission types defined."""
        for requirements in HANDS_ON_REQUIREMENTS.values():
            for req in requirements:
                assert req.submission_type is not None

    def test_all_requirements_have_names(self):
        """All requirements have names defined."""
        for requirements in HANDS_ON_REQUIREMENTS.values():
            for req in requirements:
                assert req.name
                assert len(req.name) > 0

    def test_all_requirements_have_descriptions(self):
        """All requirements have descriptions defined."""
        for requirements in HANDS_ON_REQUIREMENTS.values():
            for req in requirements:
                assert req.description
                assert len(req.description) > 0


class TestGetRequirementsForPhase:
    """Test get_requirements_for_phase function."""

    def test_returns_list_for_valid_phase(self):
        """Returns list of requirements for valid phase."""
        requirements = get_requirements_for_phase(0)
        assert isinstance(requirements, list)
        assert len(requirements) > 0

    def test_returns_empty_list_for_invalid_phase(self):
        """Returns empty list for invalid phase."""
        requirements = get_requirements_for_phase(99)
        assert requirements == []

    def test_phase_0_has_one_requirement(self):
        """Phase 0 has 1 hands-on requirement per spec."""
        requirements = get_requirements_for_phase(0)
        assert len(requirements) == 1
        assert requirements[0].id == "phase0-github-profile"

    def test_phase_5_has_four_requirements(self):
        """Phase 5 has 4 hands-on requirements per spec."""
        requirements = get_requirements_for_phase(5)
        assert len(requirements) == 4

        requirement_ids = {r.id for r in requirements}
        expected_ids = {
            "phase5-container-image",
            "phase5-cicd-pipeline",
            "phase5-terraform-iac",
            "phase5-kubernetes-manifests",
        }
        assert requirement_ids == expected_ids


class TestGetRequirementById:
    """Test get_requirement_by_id function."""

    def test_returns_requirement_for_valid_id(self):
        """Returns requirement for valid ID."""
        requirement = get_requirement_by_id("phase0-github-profile")
        assert requirement is not None
        assert requirement.id == "phase0-github-profile"
        assert requirement.phase_id == 0

    def test_returns_none_for_invalid_id(self):
        """Returns None for invalid ID."""
        requirement = get_requirement_by_id("invalid-id")
        assert requirement is None

    @pytest.mark.parametrize(
        "requirement_id,expected_phase",
        [
            ("phase0-github-profile", 0),
            ("phase1-profile-readme", 1),
            ("phase2-journal-starter-fork", 2),
            ("phase3-copilot-demo", 3),
            ("phase4-deployed-journal", 4),
            ("phase5-container-image", 5),
            ("phase6-security-scanning", 6),
        ],
    )
    def test_finds_known_requirements(self, requirement_id, expected_phase):
        """Finds known requirements by ID."""
        requirement = get_requirement_by_id(requirement_id)
        assert requirement is not None
        assert requirement.id == requirement_id
        assert requirement.phase_id == expected_phase

    def test_returns_none_for_empty_string(self):
        """Returns None for empty string ID."""
        requirement = get_requirement_by_id("")
        assert requirement is None
