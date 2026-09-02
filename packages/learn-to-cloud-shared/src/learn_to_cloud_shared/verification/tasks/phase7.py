"""Phase 7 task definitions: career reflection rubric grading.

Phase 7 (Interview & Job Prep) has no deterministic checks. The learner's
free-text answers to the three reflection questions are graded entirely by the
LLM rubric grader, using the submitted text itself as evidence.
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    RubricCriterion,
    VerificationTask,
)

PHASE7_REQUIREMENT_SLUG = "career-reflection"

CAREER_REFLECTION_RUBRIC_TASK = VerificationTask(
    id="career-reflection-rubric",
    phase_id=7,
    requirement_slug=PHASE7_REQUIREMENT_SLUG,
    name="Career Reflection Review",
    criteria=[
        RubricCriterion(
            id="complete-responses",
            label="All reflections completed",
            instruction="All three reflection questions have substantive answers.",
        ),
        RubricCriterion(
            id="personal-specificity",
            label="Specific and personal",
            instruction=(
                "Each answer draws on the learner's experience, projects, or "
                "target roles instead of giving generic advice."
            ),
        ),
        RubricCriterion(
            id="behavioral-example",
            label="Concrete behavioral example",
            instruction=(
                "The behavioral answer describes a situation, the learner's "
                "actions, and the outcome."
            ),
        ),
        RubricCriterion(
            id="target-role",
            label="Target role and skills",
            instruction=(
                "The target-role answer names a real role and specific skills "
                "the learner has or needs to build."
            ),
        ),
        RubricCriterion(
            id="project-interest",
            label="Specific project interest",
            instruction=(
                "The project answer describes a specific project and why it "
                "interests the learner."
            ),
        ),
        RubricCriterion(
            id="original-submission",
            label="Original and substantive",
            instruction=(
                "The answers are not empty, copied, placeholder, or obviously "
                "low effort."
            ),
        ),
    ],
    grading_instructions=["Grade only the submitted reflection text provided."],
    evidence=EvidencePolicy(
        source="submitted_text",
        max_files=1,
        max_file_size_bytes=20 * 1024,
        max_total_bytes=20 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase7-career-reflection-v2",
        prompt_version="2026-09-02",
        passing_score=0.6,
        model="gpt-5-mini",
    ),
)

PHASE7_TASKS: list[VerificationTask] = []
PHASE7_LLM_TASKS = [CAREER_REFLECTION_RUBRIC_TASK]
