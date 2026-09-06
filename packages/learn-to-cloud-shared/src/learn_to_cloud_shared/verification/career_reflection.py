"""Phase 7 career reflection verification.

The learner answers three reflection questions in an in-app textarea. There is
no repository to inspect, so the deterministic stage only confirms that text was
submitted; the real judgement is delegated to the LLM rubric grader, which reads
the submitted text as its evidence.
"""

from __future__ import annotations

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.evidence import collect_submitted_text_evidence
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    VerificationTask,
)

_REFLECTION_EVIDENCE_PATH = "career-reflection.md"


def validate_career_reflection(submitted_text: str) -> ValidationResult:
    """Deterministic gate for the career reflection submission.

    Passes whenever the learner submitted non-empty text. The LLM rubric grader
    makes the real pass/fail decision; this stage only guards against empty
    submissions reaching the grader.
    """
    if not submitted_text.strip():
        return ValidationResult(
            is_valid=False,
            message=(
                "Your reflection was empty. Answer all three questions and "
                "submit again."
            ),
        )

    return ValidationResult(
        is_valid=True,
        message="Reflection received. Reviewing your answers.",
    )


def collect_career_reflection_evidence(
    submitted_text: str,
    task: VerificationTask,
) -> EvidenceBundle:
    """Build a single-item evidence bundle from the submitted reflection text."""
    return collect_submitted_text_evidence(
        task,
        submitted_text,
        _REFLECTION_EVIDENCE_PATH,
    )
