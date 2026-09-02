"""Phase 5 DevOps verification configuration."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    RubricCriterion,
    VerificationTask,
)

PHASE5_REQUIREMENT_SLUG = "devops-implementation"

PHASE5_REQUIRED_PATHS = (
    "Dockerfile",
    ".github/workflows/",
    "infra/",
    "k8s/deployment.yaml",
    "k8s/service.yaml",
)

# Exact paths lead so critical files survive the combined evidence cap.
PHASE5_EVIDENCE_PATH_PATTERNS = (
    "Dockerfile",
    ".dockerignore",
    "k8s/deployment.yaml",
    "k8s/service.yaml",
    "k8s/secrets.yaml.example",
    ".github/workflows/",
    "infra/",
    "k8s/",
)

PHASE5_MAX_EVIDENCE_FILES = 24
PHASE5_MAX_FILE_SIZE_BYTES = 50 * 1024
PHASE5_MAX_TOTAL_CONTENT_BYTES = 200 * 1024


DEVOPS_IMPLEMENTATION_RUBRIC_TASK = VerificationTask(
    id="devops-implementation-rubric",
    phase_id=5,
    requirement_slug=PHASE5_REQUIREMENT_SLUG,
    name="DevOps Implementation Review",
    criteria=[
        RubricCriterion(
            id="container-image",
            label="Application container",
            instruction=(
                "The Dockerfile uses an appropriate Python base image, installs "
                "dependencies reproducibly with uv, copies the app, exposes port "
                "8000, and starts the API with uvicorn."
            ),
        ),
        RubricCriterion(
            id="delivery-workflow",
            label="CI/CD workflow",
            instruction=(
                "CI/CD runs tests, builds and pushes the image, and deploys the "
                "Kubernetes manifests from main or an equivalent protected flow."
            ),
        ),
        RubricCriterion(
            id="cloud-infrastructure",
            label="Cloud infrastructure",
            instruction=(
                "Terraform provisions a container registry, managed Kubernetes, "
                "managed PostgreSQL, and the role needed to pull images."
            ),
        ),
        RubricCriterion(
            id="kubernetes-runtime",
            label="Kubernetes runtime",
            instruction=(
                "Kubernetes defines a Deployment and Service, injects secrets "
                "without real committed credentials, and configures health probes "
                "and port 8000 routing."
            ),
        ),
        RubricCriterion(
            id="delivery-coherence",
            label="End-to-end coherence",
            instruction=(
                "CI builds the image Kubernetes deploys, Terraform provisions "
                "referenced services, and container, probe, and Service ports agree."
            ),
        ),
        RubricCriterion(
            id="deployable-configuration",
            label="Deployable and safe configuration",
            instruction=(
                "The files contain no hardcoded credentials, placeholder-only "
                "resources, contradictions, or configurations that cannot "
                "plausibly deploy the Journal API."
            ),
        ),
    ],
    grading_instructions=[
        (
            "Review the Dockerfile, CI/CD workflows, Terraform, and Kubernetes "
            "manifests together as one production delivery system."
        ),
        (
            "Treat the required-files and public-GHCR checks as trusted passing "
            "gates; do not re-grade whether files or the image exist."
        ),
        (
            "Accept equivalent valid cloud-provider syntax and file organization "
            "when the evidence satisfies the same operational requirements."
        ),
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=list(PHASE5_EVIDENCE_PATH_PATTERNS),
        required_files=list(PHASE5_REQUIRED_PATHS),
        max_files=PHASE5_MAX_EVIDENCE_FILES,
        max_file_size_bytes=PHASE5_MAX_FILE_SIZE_BYTES,
        max_total_bytes=PHASE5_MAX_TOTAL_CONTENT_BYTES,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase5-devops-implementation-v2",
        prompt_version="2026-09-02",
        passing_score=0.8,
        model="gpt-5-mini",
    ),
)

PHASE5_LLM_TASKS = [DEVOPS_IMPLEMENTATION_RUBRIC_TASK]
