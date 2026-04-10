"""Phase 3 Pydantic models for structured LLM output.

Contains the grade model used by PR diff grading and the shared
``MAX_FILE_SIZE_BYTES`` constant.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Maximum file size to prevent token exhaustion (50KB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024


class PrDiffGrade(BaseModel):
    """Structured output for single-task PR diff grading."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(description="Whether the PR diff implements the required task")
    feedback: str = Field(
        description="1-3 sentences of specific, educational feedback",
        max_length=500,
    )
    next_steps: str = Field(
        default="",
        description="One actionable sentence: what the learner should try next",
        max_length=200,
    )
