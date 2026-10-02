"""Results returned by verification checks."""

from __future__ import annotations

from learn_to_cloud.schemas.base import FrozenModel
from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification.tasks.base import EvidenceBundle, VerificationTask


class GradingEvidence(FrozenModel):
    """Evidence a check collected for rubric grading."""

    task: VerificationTask
    bundle: EvidenceBundle


class CheckResult(FrozenModel):
    """A check's deterministic result, plus evidence when it requests grading."""

    validation_result: ValidationResult
    grading: GradingEvidence | None = None
