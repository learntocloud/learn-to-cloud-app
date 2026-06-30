"""Phase 7 task definitions: career reflection rubric grading.

Phase 7 (Interview & Job Prep) has no deterministic checks. The learner's
free-text answers to the three reflection questions are graded entirely by the
LLM rubric grader, using the submitted text itself as evidence.
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    VerificationTask,
)

PHASE7_REQUIREMENT_SLUG = "career-reflection"

CAREER_REFLECTION_RUBRIC_TASK = VerificationTask(
    id="career-reflection-rubric",
    phase_id=7,
    requirement_slug=PHASE7_REQUIREMENT_SLUG,
    name="Career Reflection Review",
    criteria=[
        "MUST answer all three reflection questions, not just one or two",
        (
            "Each answer MUST be specific and personal, drawing on the learner's "
            "own experience, projects, or target roles rather than generic advice"
        ),
        (
            "The behavioral answer MUST describe a concrete situation, what the "
            "learner did, and the outcome"
        ),
        (
            "The target-role answer MUST reference a real role and name specific "
            "skills the learner has or needs to build"
        ),
        (
            "The project answer MUST describe a specific project and why it "
            "interests the learner"
        ),
        (
            "Reject empty, copy-pasted, placeholder, or obviously low-effort "
            "answers; grade only the submitted text provided"
        ),
    ],
    evidence=EvidencePolicy(
        source="submitted_text",
        max_files=1,
        max_file_size_bytes=20 * 1024,
        max_total_bytes=20 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase7-career-reflection-v1",
        prompt_version="2026-06-26",
        passing_score=0.6,
        model="gpt-5-mini",
    ),
)

PHASE7_TASKS: list[VerificationTask] = []
PHASE7_LLM_TASKS = [CAREER_REFLECTION_RUBRIC_TASK]
