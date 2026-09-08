"""Task definitions for verification services."""

from learn_to_cloud_shared.verification.tasks.base import (
    ApiProbeGraderConfig,
    CompositeGraderConfig,
    EvidenceBundle,
    EvidenceDirectoryRule,
    EvidenceItem,
    EvidencePolicy,
    FilePresenceGraderConfig,
    GradingResult,
    LLMGradingDecision,
    LLMRubricGraderConfig,
    RubricCriterion,
    TokenGraderConfig,
    VerificationTask,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    PHASE6_LLM_TASKS,
    PHASE6_REQUIREMENT_SLUG,
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
    PHASE7_LLM_TASKS,
    PHASE7_REQUIREMENT_SLUG,
    PHASE7_TASKS,
)

__all__ = [
    "ApiProbeGraderConfig",
    "CompositeGraderConfig",
    "EvidenceBundle",
    "EvidenceDirectoryRule",
    "EvidenceItem",
    "EvidencePolicy",
    "FilePresenceGraderConfig",
    "GradingResult",
    "LLMGradingDecision",
    "LLMRubricGraderConfig",
    "RubricCriterion",
    "PHASE6_REQUIREMENT_SLUG",
    "PHASE6_LLM_TASKS",
    "CAREER_REFLECTION_RUBRIC_TASK",
    "PHASE7_REQUIREMENT_SLUG",
    "PHASE7_LLM_TASKS",
    "PHASE7_TASKS",
    "SECURITY_SCANNING_RUBRIC_TASK",
    "TokenGraderConfig",
    "VerificationTask",
    "require_llm_rubric_grader",
]
