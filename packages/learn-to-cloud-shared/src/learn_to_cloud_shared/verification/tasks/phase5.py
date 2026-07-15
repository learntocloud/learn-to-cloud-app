"""Phase 5 DevOps verification configuration."""

from __future__ import annotations

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
