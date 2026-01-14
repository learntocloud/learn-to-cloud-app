"""Hands-on verification orchestration module.

This module provides the central orchestration for all hands-on verification:
- Defines all hands-on requirements per phase (HANDS_ON_REQUIREMENTS)
- Routes submissions to appropriate validators
- Provides lookup functions for requirements

EXTENSIBILITY:
To add a new verification type:
1. Add the SubmissionType enum value in models.py
2. Add optional fields to HandsOnRequirement in schemas.py if needed
3. Create a validator function (here or in a new module):
   - async def validate_<type>(url: str, ...) -> ValidationResult
4. Add routing case in validate_submission() below

For GitHub-specific validations, see github_hands_on_verification.py
For CTF token validation, see ctf.py
"""

import asyncio
import logging
import socket
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit

import httpx

from .ctf import verify_ctf_token
from .github_hands_on_verification import (
    ValidationResult,
    validate_github_profile,
    validate_profile_readme,
    validate_repo_fork,
    validate_repo_url,
)
from models import SubmissionType
from schemas import HandsOnRequirement
from core.telemetry import track_dependency

logger = logging.getLogger(__name__)

def _is_public_ip(ip_str: str) -> bool:
    """Return True if the IP is publicly routable (not private/loopback/etc)."""
    try:
        ip_obj = ip_address(ip_str)
    except ValueError:
        return False

    is_global = getattr(ip_obj, "is_global", None)
    if callable(is_global):
        return bool(is_global())

    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )

async def _host_resolves_to_public_ip(host: str) -> bool:
    """Resolve host and ensure all A/AAAA records are publicly routable."""
    try:
        ip_address(host)
        return _is_public_ip(host)
    except ValueError:
        pass

    def _resolve() -> list[str]:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        addrs: set[str] = set()
        for family, _, _, _, sockaddr in results:
            if family == socket.AF_INET:
                addrs.add(sockaddr[0])
            elif family == socket.AF_INET6:
                addrs.add(sockaddr[0])
        return sorted(addrs)

    try:
        addresses = await asyncio.to_thread(_resolve)
    except socket.gaierror:
        return False

    if not addresses:
        return False

    return all(_is_public_ip(addr) for addr in addresses)

async def _validate_public_https_url(url: str) -> str:
    """Validate an untrusted URL is HTTPS and resolves to public IPs."""
    url = url.strip()
    parts = urlsplit(url)

    if parts.scheme != "https":
        raise ValueError("URL must use https")
    if not parts.netloc:
        raise ValueError("URL must include a host")
    if parts.username or parts.password:
        raise ValueError("URL must not include credentials")

    hostname = parts.hostname
    if not hostname:
        raise ValueError("URL host is invalid")

    is_public = await _host_resolves_to_public_ip(hostname)
    if not is_public:
        raise ValueError("URL host is not publicly routable")

    return parts._replace(fragment="").geturl()

HANDS_ON_REQUIREMENTS: dict[int, list[HandsOnRequirement]] = {
    0: [
        HandsOnRequirement(
            id="phase0-github-profile",
            phase_id=0,
            submission_type=SubmissionType.GITHUB_PROFILE,
            name="GitHub Profile",
            description="Create a GitHub account and submit your profile URL. This is where you'll store all your code and projects throughout your cloud journey.",
            example_url="https://github.com/madebygps",
        ),
    ],
    1: [
        HandsOnRequirement(
            id="phase1-profile-readme",
            phase_id=1,
            submission_type=SubmissionType.PROFILE_README,
            name="GitHub Profile README",
            description="Create a GitHub profile README to introduce yourself. This should be in a repo named after your username.",
            example_url="https://github.com/madebygps/madebygps/blob/main/README.md",
        ),
        HandsOnRequirement(
            id="phase1-linux-ctfs-fork",
            phase_id=1,
            submission_type=SubmissionType.REPO_FORK,
            name="Linux CTFs Repository Fork",
            description="Fork the Linux CTFs repository to complete the hands-on challenges.",
            example_url="https://github.com/madebygps/linux-ctfs",
            required_repo="learntocloud/linux-ctfs",
        ),
        HandsOnRequirement(
            id="phase1-linux-ctf-token",
            phase_id=1,
            submission_type=SubmissionType.CTF_TOKEN,
            name="Linux CTF Completion Token",
            description="Complete all 18 Linux CTF challenges and submit your verification token. The token is generated after completing all challenges in the CTF environment.",
            example_url=None,
        ),
    ],
    2: [
        HandsOnRequirement(
            id="phase2-journal-starter-fork",
            phase_id=2,
            submission_type=SubmissionType.REPO_FORK,
            name="Learning Journal Capstone Project",
            description="Fork the journal-starter repository and build your Learning Journal API with FastAPI, PostgreSQL, and AI-powered entry analysis.",
            example_url="https://github.com/learntocloud/journal-starter",
            required_repo="learntocloud/journal-starter",
        ),
    ],
    3: [
        HandsOnRequirement(
            id="phase3-copilot-demo",
            phase_id=3,
            submission_type=SubmissionType.REPO_URL,
            name="GitHub Copilot Demonstration",
            description="Create a repository demonstrating GitHub Copilot usage with documented examples of AI-assisted coding.",
            example_url="https://github.com/yourusername/copilot-demo",
        ),
    ],
    4: [
        HandsOnRequirement(
            id="phase4-deployed-journal",
            phase_id=4,
            submission_type=SubmissionType.DEPLOYED_APP,
            name="Deployed Journal API",
            description="Deploy your Learning Journal API to Azure (or another cloud provider) and submit the live URL. The app should have a working /entries endpoint.",
            example_url="https://my-journal-api.azurewebsites.net",
            expected_endpoint="/entries",
        ),
    ],
    5: [
        HandsOnRequirement(
            id="phase5-dockerized-app",
            phase_id=5,
            submission_type=SubmissionType.REPO_URL,
            name="Dockerized Application",
            description="Containerize your Journal API with a Dockerfile and docker-compose.yml. Submit the repository URL.",
            example_url="https://github.com/yourusername/journal-api",
        ),
        HandsOnRequirement(
            id="phase5-cicd-pipeline",
            phase_id=5,
            submission_type=SubmissionType.REPO_URL,
            name="CI/CD Pipeline",
            description="Set up a CI/CD pipeline (GitHub Actions, Azure DevOps, etc.) that builds, tests, and deploys your application.",
            example_url="https://github.com/yourusername/journal-api/actions",
        ),
    ],
    6: [
        HandsOnRequirement(
            id="phase6-security-scanning",
            phase_id=6,
            submission_type=SubmissionType.REPO_URL,
            name="Security Scanning Setup",
            description="Enable security scanning on one of your repositories (Dependabot, CodeQL, or cloud security tools) and show resolved or triaged findings.",
            example_url="https://github.com/yourusername/journal-api/security",
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

@track_dependency("deployed_app_check", "HTTP")
async def validate_deployed_app(
    app_url: str, expected_endpoint: str | None = None
) -> ValidationResult:
    """
    Validate a deployed application by making a GET request.

    Args:
        app_url: The base URL of the deployed app (e.g., https://my-app.azurewebsites.net)
        expected_endpoint: Optional endpoint to append (e.g., "/entries")

    Returns:
        ValidationResult indicating if the app is accessible
    """
    app_url = app_url.strip().rstrip("/")

    if expected_endpoint:
        if not expected_endpoint.startswith("/"):
            expected_endpoint = "/" + expected_endpoint
        check_url = app_url + expected_endpoint
    else:
        check_url = app_url

    try:
        max_redirects = 5
        current_url = check_url

        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
            for redirect_count in range(max_redirects + 1):
                safe_url = await _validate_public_https_url(current_url)

                async with client.stream("GET", safe_url) as response:
                    status_code = response.status_code
                    location = response.headers.get("location")

                if status_code in (301, 302, 303, 307, 308):
                    if not location:
                        return ValidationResult(
                            is_valid=False,
                            message="App returned a redirect without a Location header.",
                            username_match=True,
                            repo_exists=False,
                        )
                    current_url = urljoin(safe_url, location)
                    continue

                if status_code == 200:
                    return ValidationResult(
                        is_valid=True,
                        message=f"App is live! Successfully reached {safe_url}",
                        username_match=True,
                        repo_exists=True,
                    )

                if status_code in (401, 403):
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            f"App is running but {expected_endpoint or '/'} requires authentication. "
                            "Make sure the endpoint is publicly accessible without auth."
                        ),
                        username_match=True,
                        repo_exists=True,
                    )

                if status_code == 404:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            f"Endpoint not found (404). Make sure your app has a {expected_endpoint or '/'} endpoint."
                        ),
                        username_match=True,
                        repo_exists=False,
                    )

                return ValidationResult(
                    is_valid=False,
                    message=f"App returned status {status_code}. Expected 200 OK.",
                    username_match=True,
                    repo_exists=False,
                )

        return ValidationResult(
            is_valid=False,
            message="Too many redirects while trying to reach your app.",
            username_match=True,
            repo_exists=False,
        )

    except httpx.TimeoutException:
        return ValidationResult(
            is_valid=False,
            message="Request timed out. Is your app running and accessible from the internet?",
            username_match=True,
            repo_exists=False,
        )
    except httpx.ConnectError:
        return ValidationResult(
            is_valid=False,
            message="Could not connect to your app. Check that the URL is correct and the app is deployed.",
            username_match=True,
            repo_exists=False,
        )
    except ValueError as e:
        return ValidationResult(
            is_valid=False,
            message=str(e),
            username_match=True,
            repo_exists=False,
        )
    except httpx.RequestError as e:
        logger.warning(f"Error checking deployed app {check_url}: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Request error: {str(e)}",
            username_match=True,
            repo_exists=False,
        )

def validate_ctf_token_submission(
    token: str, expected_username: str
) -> ValidationResult:
    """
    Validate a CTF token submission.

    Args:
        token: The base64-encoded CTF completion token
        expected_username: The expected GitHub username from OAuth

    Returns:
        ValidationResult with verification status
    """
    ctf_result = verify_ctf_token(token, expected_username)

    return ValidationResult(
        is_valid=ctf_result.is_valid,
        message=ctf_result.message,
        username_match=ctf_result.is_valid,
        repo_exists=ctf_result.is_valid,
    )

async def validate_submission(
    requirement: HandsOnRequirement,
    submitted_value: str,
    expected_username: str | None = None,
) -> ValidationResult:
    """
    Validate a submission based on its requirement type.

    This is the main entry point for validating any hands-on submission.
    It routes to the appropriate validator based on the submission type.

    To add a new verification type:
    1. Add the SubmissionType enum value in models.py
    2. Implement the validator function
    3. Add the routing case below

    Args:
        requirement: The requirement being validated
        submitted_value: The value submitted by the user (URL, token, or challenge response)
        expected_username: The expected GitHub username (required for GitHub-based validations)
    """
    if requirement.submission_type == SubmissionType.PROFILE_README:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for profile README validation",
                username_match=False,
                repo_exists=False,
            )
        return await validate_profile_readme(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.REPO_FORK:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for repository fork validation",
                username_match=False,
                repo_exists=False,
            )
        if not requirement.required_repo:
            return ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=False,
                repo_exists=False,
            )
        return await validate_repo_fork(
            submitted_value, expected_username, requirement.required_repo
        )

    elif requirement.submission_type == SubmissionType.DEPLOYED_APP:
        return await validate_deployed_app(submitted_value, requirement.expected_endpoint)

    elif requirement.submission_type == SubmissionType.CTF_TOKEN:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for CTF token validation",
                username_match=False,
                repo_exists=False,
            )
        return validate_ctf_token_submission(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.GITHUB_PROFILE:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for profile validation",
                username_match=False,
                repo_exists=False,
            )
        return await validate_github_profile(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.REPO_URL:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for repository validation",
                username_match=False,
                repo_exists=False,
            )
        return await validate_repo_url(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.API_CHALLENGE:
        return ValidationResult(
            is_valid=False,
            message="API challenge verification is not yet implemented",
            username_match=False,
            repo_exists=False,
        )

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )
