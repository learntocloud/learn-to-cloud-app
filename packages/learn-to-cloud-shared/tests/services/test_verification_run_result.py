"""Verification outcome contracts."""

import pytest

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification_workflow import outcome_for_validation


@pytest.mark.unit
@pytest.mark.parametrize("is_valid", [False, True])
def test_incomplete_result_never_counts_as_completed(is_valid):
    assert (
        outcome_for_validation(
            ValidationResult(
                is_valid=is_valid,
                verification_completed=False,
                message="Verification did not finish.",
                error_code="evidence.selection",
            )
        )
        == "server_error"
    )
