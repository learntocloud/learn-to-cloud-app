"""Phase hands-on requirements definitions.

This module contains the hands-on requirements for Phase 0 and Phase 1.
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

from models import SubmissionType
from schemas import HandsOnRequirement

HANDS_ON_REQUIREMENTS: dict[int, list[HandsOnRequirement]] = {
    0: [
        HandsOnRequirement(
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
        HandsOnRequirement(
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
        HandsOnRequirement(
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
        HandsOnRequirement(
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
        HandsOnRequirement(
            id="phase2-troubleshooting-report",
            phase_id=2,
            submission_type=SubmissionType.FREE_TEXT,
            name="Network Troubleshooting Report",
            description=(
                "Complete the Network Troubleshooting Lab and submit a report "
                "documenting at least 3 issues you diagnosed, the commands you used, "
                "and how you fixed each problem."
            ),
            example_url=None,
        ),
    ],
    3: [
        HandsOnRequirement(
            id="phase3-journal-fork",
            phase_id=3,
            submission_type=SubmissionType.REPO_FORK,
            name="Journal Starter Repository Fork",
            description=(
                "Fork the Journal Starter repository to begin the capstone project. "
                "This FastAPI + PostgreSQL application will help you practice "
                "Python API development skills."
            ),
            example_url="https://github.com/madebygps/journal-starter",
            required_repo="learntocloud/journal-starter",
        ),
        HandsOnRequirement(
            id="phase3-code-analysis",
            phase_id=3,
            submission_type=SubmissionType.CODE_ANALYSIS,
            name="Journal API Implementation",
            description=(
                "Complete all required tasks in your Journal Starter fork and submit "
                "your repository URL for code verification."
            ),
            example_url="https://github.com/madebygps/journal-starter",
            note="You can only verify once per hour.",
        ),
    ],
}


def get_requirements_for_phase(phase_id: int) -> list[HandsOnRequirement]:
    """Get all hands-on requirements for a specific phase."""
    return HANDS_ON_REQUIREMENTS.get(phase_id, [])


def get_requirement_by_id(requirement_id: str) -> HandsOnRequirement | None:
    """Get a specific requirement by its ID."""
    for requirements in HANDS_ON_REQUIREMENTS.values():
        for req in requirements:
            if req.id == requirement_id:
                return req
    return None
