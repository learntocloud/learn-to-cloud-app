"""Phase 5 DevOps verification configuration."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
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
        (
            "Review the supplied Dockerfile, CI/CD workflows, Terraform, and "
            "Kubernetes manifests together as one production delivery system"
        ),
        (
            "Dockerfile MUST use an appropriate Python base image, install "
            "dependencies reproducibly with uv, copy the application, expose "
            "port 8000, and start the API with uvicorn"
        ),
        (
            "CI/CD MUST run tests, build and push the application image, and "
            "deploy the Kubernetes manifests from the main branch or an "
            "equivalent protected delivery flow"
        ),
        (
            "Terraform MUST provision the core cloud dependencies: container "
            "registry, managed Kubernetes cluster, managed PostgreSQL, and the "
            "IAM or role binding needed for the cluster to pull images"
        ),
        (
            "Kubernetes MUST define a Deployment and Service, inject secrets "
            "without committed real credentials, and configure health probes "
            "and port routing for the API on port 8000"
        ),
        (
            "The files MUST be coherent across boundaries: CI builds the image "
            "the manifests deploy, Terraform provisions the services the "
            "workflow and manifests reference, and container, probe, and "
            "Service ports agree"
        ),
        (
            "MUST reject hardcoded credentials, placeholder-only resources, "
            "internally contradictory files, or configurations that cannot "
            "plausibly build and deploy the Journal API"
        ),
        (
            "MUST treat the required-files and public-GHCR checks as trusted "
            "passing gates; do not re-grade whether files or the image exist"
        ),
        (
            "Feedback MUST concisely summarize Dockerfile, CI/CD, Terraform, "
            "Kubernetes, and overall coherence findings"
        ),
        (
            "SHOULD accept equivalent valid cloud-provider syntax and file "
            "organization when the supplied evidence clearly satisfies the "
            "same operational requirements"
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
        rubric_id="phase5-devops-implementation-v1",
        prompt_version="2026-07-15",
        passing_score=0.8,
        model="gpt-5-mini",
    ),
)

PHASE5_LLM_TASKS = [DEVOPS_IMPLEMENTATION_RUBRIC_TASK]
