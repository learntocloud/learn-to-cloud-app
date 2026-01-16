"""Phase hands-on requirements definitions.

This module contains all the hands-on requirements for each phase.
Requirements are configuration data that define what users must complete
to finish each phase's hands-on activities.

Each requirement specifies:
- id: Unique identifier for the requirement
- phase_id: Which phase this belongs to
- submission_type: How the submission should be validated
- name: Display name for the UI
- description: Instructions shown to the user
- example_url: Example of what a valid submission looks like
- Additional fields for specific validation types

To add a new requirement:
1. Add it to the appropriate phase in HANDS_ON_REQUIREMENTS
2. Use an existing SubmissionType or add a new one in models.py
3. If needed, add fields to HandsOnRequirement in schemas.py
"""

from dataclasses import dataclass

from models import SubmissionType


@dataclass(frozen=True)
class HandsOnRequirementData:
    """Hands-on requirement definition used by the services layer.

    NOTE: This is intentionally a dataclass (not a Pydantic schema) to keep
    the services layer independent from the routes/schema layer.
    """

    id: str
    phase_id: int
    submission_type: SubmissionType
    name: str
    description: str
    example_url: str | None = None

    required_repo: str | None = None
    expected_endpoint: str | None = None

    # If True, validate the response body matches Journal API structure
    validate_response_body: bool = False

    challenge_config: dict | None = None

    # For REPO_WITH_FILES: file patterns to search for
    required_file_patterns: list[str] | None = None
    # Human-readable description of the files being searched for
    file_description: str | None = None


HANDS_ON_REQUIREMENTS: dict[int, list[HandsOnRequirementData]] = {
    0: [
        HandsOnRequirementData(
            id="phase0-github-profile",
            phase_id=0,
            submission_type=SubmissionType.GITHUB_PROFILE,
            name="GitHub Profile",
            description=(
                "Create a GitHub account and submit your profile URL. "
                "This is where you'll store all your code and projects "
                "throughout your cloud journey."
            ),
            example_url="https://github.com/madebygps",
        ),
    ],
    1: [
        HandsOnRequirementData(
            id="phase1-profile-readme",
            phase_id=1,
            submission_type=SubmissionType.PROFILE_README,
            name="GitHub Profile README",
            description=(
                "Create a GitHub profile README to introduce yourself. "
                "This should be in a repo named after your username."
            ),
            example_url="https://github.com/madebygps/madebygps/blob/main/README.md",
        ),
        HandsOnRequirementData(
            id="phase1-linux-ctfs-fork",
            phase_id=1,
            submission_type=SubmissionType.REPO_FORK,
            name="Linux CTFs Repository Fork",
            description=(
                "Fork the Linux CTFs repository to complete the hands-on challenges."
            ),
            example_url="https://github.com/madebygps/linux-ctfs",
            required_repo="learntocloud/linux-ctfs",
        ),
        HandsOnRequirementData(
            id="phase1-linux-ctf-token",
            phase_id=1,
            submission_type=SubmissionType.CTF_TOKEN,
            name="Linux CTF Completion Token",
            description=(
                "Complete all 18 Linux CTF challenges and submit your "
                "verification token. The token is generated after "
                "completing all challenges in the CTF environment."
            ),
            example_url=None,
        ),
    ],
    2: [
        HandsOnRequirementData(
            id="phase2-journal-starter-fork",
            phase_id=2,
            submission_type=SubmissionType.REPO_FORK,
            name="Learning Journal Capstone Project",
            description=(
                "Fork the journal-starter repository and build your "
                "Learning Journal API with FastAPI, PostgreSQL, and "
                "AI-powered entry analysis."
            ),
            example_url="https://github.com/learntocloud/journal-starter",
            required_repo="learntocloud/journal-starter",
        ),
        HandsOnRequirementData(
            id="phase2-journal-api-working",
            phase_id=2,
            submission_type=SubmissionType.JOURNAL_API_RESPONSE,
            name="Working Journal API",
            description=(
                "Verify your Journal API is working locally. Create at "
                "least one journal entry using POST /entries, then call "
                "GET /entries and paste the JSON response below."
            ),
            example_url=None,
        ),
    ],
    3: [
        HandsOnRequirementData(
            id="phase3-copilot-demo",
            phase_id=3,
            submission_type=SubmissionType.REPO_URL,
            name="GitHub Copilot Demonstration",
            description=(
                "Create a repository demonstrating GitHub Copilot usage "
                "with documented examples of AI-assisted coding."
            ),
            example_url="https://github.com/yourusername/copilot-demo",
        ),
    ],
    4: [
        HandsOnRequirementData(
            id="phase4-deployed-journal",
            phase_id=4,
            submission_type=SubmissionType.DEPLOYED_APP,
            name="Deployed Journal API",
            description=(
                "Deploy your Learning Journal API to a cloud provider "
                "and submit the live URL. We'll call your GET /entries "
                "endpoint and verify the response has valid journal "
                "entries. Make sure the endpoint is publicly accessible "
                "(no authentication required)."
            ),
            example_url="https://my-journal-api.azurewebsites.net",
            expected_endpoint="/entries",
            validate_response_body=True,
        ),
    ],
    5: [
        HandsOnRequirementData(
            id="phase5-container-image",
            phase_id=5,
            submission_type=SubmissionType.CONTAINER_IMAGE,
            name="Container Image Published",
            description=(
                "Push your containerized Journal API to a public "
                "container registry (Docker Hub or GitHub Container "
                "Registry). We'll verify the image exists and is "
                "publicly accessible."
            ),
            example_url="docker.io/yourusername/journal-api:latest",
        ),
        HandsOnRequirementData(
            id="phase5-cicd-pipeline",
            phase_id=5,
            submission_type=SubmissionType.WORKFLOW_RUN,
            name="CI/CD Pipeline",
            description=(
                "Set up a CI/CD pipeline using GitHub Actions "
                "(`.github/workflows/`) that builds, tests, and deploys "
                "your application. We'll verify a workflow has completed "
                "successfully in the last 30 days."
            ),
            example_url="https://github.com/yourusername/journal-api",
        ),
        HandsOnRequirementData(
            id="phase5-terraform-iac",
            phase_id=5,
            submission_type=SubmissionType.REPO_WITH_FILES,
            name="Infrastructure as Code",
            description=(
                "Create Terraform configuration files in an `infra/` "
                "directory to provision your cloud infrastructure. "
                "Required files: main.tf, variables.tf."
            ),
            example_url="https://github.com/yourusername/journal-api",
            required_file_patterns=["infra/main.tf", "infra/variables.tf", "infra/"],
            file_description="Terraform files in infra/ directory",
        ),
        HandsOnRequirementData(
            id="phase5-kubernetes-manifests",
            phase_id=5,
            submission_type=SubmissionType.REPO_WITH_FILES,
            name="Kubernetes Manifests",
            description=(
                "Create Kubernetes manifests in a `k8s/` directory with "
                "at least a Deployment and Service. Required files: "
                "k8s/deployment.yaml, k8s/service.yaml."
            ),
            example_url="https://github.com/yourusername/journal-api",
            required_file_patterns=["k8s/deployment", "k8s/service"],
            file_description="Kubernetes manifests in k8s/ directory",
        ),
    ],
    6: [
        HandsOnRequirementData(
            id="phase6-security-scanning",
            phase_id=6,
            submission_type=SubmissionType.REPO_URL,
            name="Security Scanning Setup",
            description=(
                "Enable security scanning on one of your repositories "
                "(Dependabot, CodeQL, or cloud security tools) and show "
                "resolved or triaged findings."
            ),
            example_url="https://github.com/yourusername/journal-api/security",
        ),
    ],
}


def get_requirements_for_phase(phase_id: int) -> list[HandsOnRequirementData]:
    """Get all hands-on requirements for a specific phase."""
    return HANDS_ON_REQUIREMENTS.get(phase_id, [])


def get_requirement_by_id(requirement_id: str) -> HandsOnRequirementData | None:
    """Get a specific requirement by its ID."""
    for requirements in HANDS_ON_REQUIREMENTS.values():
        for req in requirements:
            if req.id == requirement_id:
                return req
    return None
