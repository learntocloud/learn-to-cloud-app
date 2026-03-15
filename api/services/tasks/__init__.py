"""Task definitions for LLM-powered verification services.

Each phase has its own module with:
- Task definitions (TypedDicts with grading rubrics)
- Pydantic models for structured LLM output
- Constants (file paths, patterns, limits)
"""

from services.tasks.phase3_tasks import (
    ALLOWED_FILE_PATHS,
    PHASE3_TASKS,
    CodeAnalysisResponse,
)
from services.tasks.phase3_tasks import (
    TaskGrade as Phase3TaskGrade,
)
from services.tasks.phase5_tasks import (
    DEVOPS_PATH_PATTERNS,
    MAX_FILES_PER_CATEGORY,
    MAX_TOTAL_CONTENT_BYTES,
    PHASE5_TASKS,
    DevOpsAnalysisLLMResponse,
)
from services.tasks.phase5_tasks import (
    DevOpsTaskGrade as Phase5TaskGrade,
)

__all__ = [
    "ALLOWED_FILE_PATHS",
    "CodeAnalysisResponse",
    "DEVOPS_PATH_PATTERNS",
    "DevOpsAnalysisLLMResponse",
    "MAX_FILES_PER_CATEGORY",
    "MAX_TOTAL_CONTENT_BYTES",
    "PHASE3_TASKS",
    "PHASE5_TASKS",
    "Phase3TaskGrade",
    "Phase5TaskGrade",
]
