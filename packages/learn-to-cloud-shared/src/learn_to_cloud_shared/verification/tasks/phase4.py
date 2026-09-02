"""Phase 4 capstone task definitions: architecture alignment rubric grading.

The learner writes a free-text description of their deployment architecture in
the app and commits an idempotent ``deploy.sh`` to their fork. The LLM rubric
grader reads both the script and the description and judges whether the
description honestly reflects what the script provisions, and whether the
result is a secure two-tier deployment.
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    RubricCriterion,
    VerificationTask,
)

PHASE4_REQUIREMENT_SLUG = "deployment-architecture"

DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK = VerificationTask(
    id="deployment-architecture-rubric",
    phase_id=4,
    requirement_slug=PHASE4_REQUIREMENT_SLUG,
    name="Deployment Architecture Alignment Review",
    criteria=[
        RubricCriterion(
            id="implementation-alignment",
            label="Architecture matches the deployment",
            instruction=(
                "The architecture description matches what deploy.sh actually "
                "provisions and does not claim unsupported resources or controls."
            ),
        ),
        RubricCriterion(
            id="two-tier-architecture",
            label="Two-tier architecture",
            instruction=(
                "deploy.sh provisions a public API tier and a separate private "
                "database tier."
            ),
        ),
        RubricCriterion(
            id="security-controls",
            label="Deployment security",
            instruction=(
                "The deployment includes meaningful controls such as a private "
                "database, restricted inbound access, or API TLS termination."
            ),
        ),
        RubricCriterion(
            id="design-specificity",
            label="Specific architecture explanation",
            instruction=(
                "The description explains the learner's networking, compute, "
                "database, and traffic flow rather than restating the task."
            ),
        ),
        RubricCriterion(
            id="substantive-submission",
            label="Substantive submission",
            instruction=(
                "The script and description are complete and are not empty, "
                "placeholder, copied, or obviously low effort."
            ),
        ),
    ],
    grading_instructions=[
        "Grade only the supplied deploy.sh and architecture description.",
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        max_files=2,
        max_file_size_bytes=30 * 1024,
        max_total_bytes=60 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase4-deployment-architecture-v2",
        prompt_version="2026-09-02",
        passing_score=0.7,
        model="gpt-5-mini",
    ),
)

PHASE4_TASKS: list[VerificationTask] = []
PHASE4_LLM_TASKS = [DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK]
