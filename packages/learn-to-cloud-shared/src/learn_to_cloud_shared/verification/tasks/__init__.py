"""Task definitions for verification services."""

from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
    EvidencePolicy,
    LLMGradingDecision,
    LLMRubricGraderConfig,
    RubricCriterion,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    PHASE6_REQUIREMENT_SLUG,
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
    PHASE7_REQUIREMENT_SLUG,
)

__all__ = [
    "EvidenceBundle",
    "EvidenceItem",
    "EvidencePolicy",
    "LLMGradingDecision",
    "LLMRubricGraderConfig",
    "RubricCriterion",
    "PHASE6_REQUIREMENT_SLUG",
    "CAREER_REFLECTION_RUBRIC_TASK",
    "PHASE7_REQUIREMENT_SLUG",
    "SECURITY_SCANNING_RUBRIC_TASK",
    "VerificationTask",
]
