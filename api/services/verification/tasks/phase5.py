"""Phase 5 task definitions: DevOps artifact verification.

Defines the 4 tasks learners must add to their journal-starter fork
(Dockerfile, CI/CD, Terraform, Kubernetes).
"""

from __future__ import annotations

from typing import TypedDict


class TaskDefinition(TypedDict):
    """Type definition for a Phase 5 verification task."""

    id: str
    name: str
    path_patterns: list[str]
    criteria: list[str]
    pass_indicators: list[str]
    fail_indicators: list[str]
    required_files: list[str]
    min_pass_count: int


# Maximum number of files to fetch per category (prevent abuse)
MAX_FILES_PER_CATEGORY: int = 10

# Maximum file size to prevent token exhaustion (50 KB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024

# Maximum total content size (200 KB)
MAX_TOTAL_CONTENT_BYTES: int = 200 * 1024


PHASE5_TASKS: list[TaskDefinition] = [
    {
        "id": "dockerfile",
        "name": "Containerization (Dockerfile)",
        "path_patterns": ["Dockerfile", "dockerfile", ".dockerignore"],
        "required_files": ["Dockerfile"],
        "criteria": [
            "MUST have a Dockerfile at the repository root",
            (
                "MUST have a FROM instruction specifying"
                " a Python base image (e.g., python:3.12-slim)"
            ),
            "MUST install uv (not pip) and use 'uv sync'",
            (
                "MUST have a CMD or ENTRYPOINT that runs"
                " uvicorn to start the application"
            ),
            "MUST set PYTHONPATH so imports resolve correctly",
            "MUST expose port 8000",
            "MUST copy application code into the image (COPY or ADD)",
            (
                "SHOULD have a .dockerignore to exclude"
                " non-production files (.git/, tests/)"
            ),
        ],
        "pass_indicators": [
            "FROM ",
            "CMD ",
            "ENTRYPOINT ",
            "COPY ",
            "EXPOSE ",
            "uv sync",
            "uv ",
            "PYTHONPATH",
            "uvicorn",
        ],
        "fail_indicators": [],
        "min_pass_count": 5,
    },
    {
        "id": "cicd-pipeline",
        "name": "CI/CD Pipeline (GitHub Actions)",
        "path_patterns": [".github/workflows/"],
        "required_files": [".github/workflows/"],
        "criteria": [
            "MUST have at least one workflow YAML in .github/workflows/",
            "MUST trigger on push to main (or pull_request)",
            ("MUST have at least 3 jobs: test, build-and-push, and deploy"),
            ("MUST have a test job that runs linting and/or tests (e.g., pytest)"),
            (
                "MUST have a build-and-push job that builds"
                " a Docker image and pushes to a registry"
            ),
            (
                "MUST have a deploy job that connects to"
                " a K8s cluster and applies manifests"
            ),
            "SHOULD tag images with commit SHA and/or 'latest'",
            (
                "SHOULD use sed or envsubst to substitute"
                " an image placeholder in K8s manifests"
            ),
        ],
        "pass_indicators": [
            "on:",
            "jobs:",
            "steps:",
            "runs-on:",
            "uses:",
            "docker",
            "kubectl",
            "pytest",
            "deploy",
        ],
        "fail_indicators": [],
        "min_pass_count": 6,
    },
    {
        "id": "terraform-iac",
        "name": "Infrastructure as Code (Terraform)",
        "path_patterns": ["infra/"],
        "required_files": ["infra/"],
        "criteria": [
            "MUST have .tf files in the infra/ directory",
            "MUST have a provider block (e.g., azurerm, aws)",
            ("MUST define a container registry resource (e.g., ACR, ECR, GCR)"),
            ("MUST define a managed Kubernetes cluster resource (e.g., AKS, EKS, GKE)"),
            (
                "MUST define a managed PostgreSQL database"
                " resource (e.g., Azure Flexible Server, RDS)"
            ),
            (
                "SHOULD define IAM or role bindings so the"
                " K8s cluster can pull from the registry"
            ),
            "SHOULD have a variables.tf with input variables",
            (
                "SHOULD have an outputs.tf exporting"
                " registry URL, DB connection, or kubeconfig"
            ),
            ("SHOULD have a providers.tf with provider and Terraform version config"),
        ],
        "pass_indicators": [
            "provider ",
            "resource ",
            "terraform {",
            "variable ",
            "output ",
            "kubernetes",
            "container_registry",
            "postgresql",
        ],
        "fail_indicators": [],
        "min_pass_count": 4,
    },
    {
        "id": "kubernetes-manifests",
        "name": "Container Orchestration (Kubernetes)",
        "path_patterns": [
            # Exact files first — guaranteed inclusion even when
            # k8s/ has many subdirectory files
            "k8s/deployment.yaml",
            "k8s/service.yaml",
            "k8s/secrets.yaml.example",
            # Fallback: any other YAML under k8s/ fills remaining capacity
            "k8s/",
        ],
        "required_files": ["k8s/deployment.yaml", "k8s/service.yaml"],
        "criteria": [
            "MUST have YAML files in the k8s/ directory",
            ("MUST have a Deployment manifest (kind: Deployment) in deployment.yaml"),
            (
                "MUST use IMAGE_PLACEHOLDER as the image"
                " reference (CI/CD substitutes the real tag)"
            ),
            (
                "MUST reference env vars from a K8s Secret"
                " via envFrom (e.g., journal-api-secrets)"
            ),
            (
                "MUST configure health probes (liveness"
                " and/or readiness) on /health port 8000"
            ),
            ("MUST have a Service manifest in service.yaml routing port 80 to 8000"),
            (
                "SHOULD have a secrets.yaml.example"
                " showing required keys (no real values)"
            ),
            "SHOULD use LoadBalancer or NodePort type",
            "SHOULD define resource limits or requests",
        ],
        "pass_indicators": [
            "kind: Deployment",
            "kind: Service",
            "containers:",
            "image:",
            "IMAGE_PLACEHOLDER",
            "envFrom",
            "secretRef",
            "livenessProbe",
            "readinessProbe",
            "/health",
            "containerPort",
        ],
        "fail_indicators": [],
        "min_pass_count": 6,
    },
]
