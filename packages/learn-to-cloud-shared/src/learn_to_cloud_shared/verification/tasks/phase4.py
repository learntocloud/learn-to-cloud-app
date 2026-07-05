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
    VerificationTask,
)

PHASE4_REQUIREMENT_SLUG = "deployment-architecture"

DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK = VerificationTask(
    id="deployment-architecture-rubric",
    phase_id=4,
    requirement_slug=PHASE4_REQUIREMENT_SLUG,
    name="Deployment Architecture Alignment Review",
    criteria=[
        (
            "The architecture description MUST align with what deploy.sh "
            "actually provisions and configures, not with an idealized or "
            "generic setup"
        ),
        (
            "Reject descriptions that claim resources, networking, or security "
            "controls that deploy.sh does not create or configure"
        ),
        (
            "deploy.sh MUST provision a two-tier architecture: a public tier "
            "for the API and a separate private tier for the database"
        ),
        (
            "The deployment MUST show meaningful security controls, for example "
            "the database not being publicly reachable, restricted inbound "
            "rules, or TLS termination for the API"
        ),
        (
            "The description MUST be specific about the learner's own design "
            "(networking, compute, database, and how traffic flows), not a "
            "generic restatement of the task"
        ),
        (
            "Reject empty, placeholder, copy-pasted, or obviously low-effort "
            "descriptions; grade only the supplied deploy.sh and description"
        ),
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        max_files=2,
        max_file_size_bytes=30 * 1024,
        max_total_bytes=60 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase4-deployment-architecture-v1",
        prompt_version="2026-07-05",
        passing_score=0.7,
        model="gpt-5-mini",
    ),
)

PHASE4_TASKS: list[VerificationTask] = []
PHASE4_LLM_TASKS = [DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK]
