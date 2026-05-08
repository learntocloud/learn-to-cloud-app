"""Phase 5 task definitions: DevOps artifact verification."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    IndicatorGraderConfig,
    VerificationTask,
)

# Maximum number of files to fetch per category (prevent abuse)
MAX_FILES_PER_CATEGORY: int = 10

# Maximum file size to prevent token exhaustion (50 KB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024

# Maximum total content size (200 KB)
MAX_TOTAL_CONTENT_BYTES: int = 200 * 1024


PHASE5_REQUIREMENT_ID = "devops-implementation"


PHASE5_TASKS: list[VerificationTask] = [
    VerificationTask(
        id="dockerfile",
        phase_id=5,
        requirement_id=PHASE5_REQUIREMENT_ID,
        name="Containerization (Dockerfile)",
        evidence=EvidencePolicy(
            source="repo_files",
            path_patterns=["Dockerfile", "dockerfile", ".dockerignore"],
            required_files=["Dockerfile"],
            max_files=MAX_FILES_PER_CATEGORY,
            max_file_size_bytes=MAX_FILE_SIZE_BYTES,
            max_total_bytes=MAX_TOTAL_CONTENT_BYTES,
        ),
        criteria=[
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
        grader=IndicatorGraderConfig(
            pass_indicators=[
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
            min_pass_count=5,
        ),
    ),
    VerificationTask(
        id="cicd-pipeline",
        phase_id=5,
        requirement_id=PHASE5_REQUIREMENT_ID,
        name="CI/CD Pipeline (GitHub Actions)",
        evidence=EvidencePolicy(
            source="repo_files",
            path_patterns=[".github/workflows/"],
            required_files=[".github/workflows/"],
            max_files=MAX_FILES_PER_CATEGORY,
            max_file_size_bytes=MAX_FILE_SIZE_BYTES,
            max_total_bytes=MAX_TOTAL_CONTENT_BYTES,
        ),
        criteria=[
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
        grader=IndicatorGraderConfig(
            pass_indicators=[
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
            min_pass_count=6,
        ),
    ),
    VerificationTask(
        id="terraform-iac",
        phase_id=5,
        requirement_id=PHASE5_REQUIREMENT_ID,
        name="Infrastructure as Code (Terraform)",
        evidence=EvidencePolicy(
            source="repo_files",
            path_patterns=["infra/"],
            required_files=["infra/"],
            max_files=MAX_FILES_PER_CATEGORY,
            max_file_size_bytes=MAX_FILE_SIZE_BYTES,
            max_total_bytes=MAX_TOTAL_CONTENT_BYTES,
        ),
        criteria=[
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
        grader=IndicatorGraderConfig(
            pass_indicators=[
                "provider ",
                "resource ",
                "terraform {",
                "variable ",
                "output ",
                "kubernetes",
                "container_registry",
                "postgresql",
            ],
            min_pass_count=4,
        ),
    ),
    VerificationTask(
        id="kubernetes-manifests",
        phase_id=5,
        requirement_id=PHASE5_REQUIREMENT_ID,
        name="Container Orchestration (Kubernetes)",
        evidence=EvidencePolicy(
            source="repo_files",
            path_patterns=[
                "k8s/deployment.yaml",
                "k8s/service.yaml",
                "k8s/secrets.yaml.example",
                "k8s/",
            ],
            required_files=["k8s/deployment.yaml", "k8s/service.yaml"],
            max_files=MAX_FILES_PER_CATEGORY,
            max_file_size_bytes=MAX_FILE_SIZE_BYTES,
            max_total_bytes=MAX_TOTAL_CONTENT_BYTES,
        ),
        criteria=[
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
        grader=IndicatorGraderConfig(
            pass_indicators=[
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
            min_pass_count=6,
        ),
    ),
]
