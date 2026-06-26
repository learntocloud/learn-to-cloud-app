"""Task definitions for verification services."""

from learn_to_cloud_shared.verification.tasks.base import (
    ApiProbeGraderConfig,
    CompositeGraderConfig,
    EvidenceBundle,
    EvidenceItem,
    EvidencePolicy,
    FilePresenceGraderConfig,
    GradingResult,
    IndicatorGraderConfig,
    LLMGradingDecision,
    LLMRubricGraderConfig,
    TokenGraderConfig,
    VerificationTask,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification.tasks.phase3 import (
    JOURNAL_API_FINAL_RUBRIC_TASK,
    PHASE3_FINAL_REQUIREMENT_SLUG,
    PHASE3_LLM_TASKS,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    PHASE5_REQUIREMENT_SLUG,
    PHASE5_TASKS,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    PHASE6_LLM_TASKS,
    PHASE6_REQUIREMENT_SLUG,
    PHASE6_TASKS,
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
    "EvidenceItem",
    "EvidencePolicy",
    "FilePresenceGraderConfig",
    "GradingResult",
    "IndicatorGraderConfig",
    "LLMGradingDecision",
    "LLMRubricGraderConfig",
    "JOURNAL_API_FINAL_RUBRIC_TASK",
    "PHASE3_FINAL_REQUIREMENT_SLUG",
    "PHASE3_LLM_TASKS",
    "PHASE5_REQUIREMENT_SLUG",
    "PHASE5_TASKS",
    "PHASE6_REQUIREMENT_SLUG",
    "PHASE6_LLM_TASKS",
    "PHASE6_TASKS",
    "CAREER_REFLECTION_RUBRIC_TASK",
    "PHASE7_REQUIREMENT_SLUG",
    "PHASE7_LLM_TASKS",
    "PHASE7_TASKS",
    "SECURITY_SCANNING_RUBRIC_TASK",
    "TokenGraderConfig",
    "VerificationTask",
    "require_llm_rubric_grader",
]
