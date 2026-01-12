"""GitHub validation utilities for hands-on verification.

Security note:
This module processes user-submitted URLs (deployed app validation). Those URLs
must be treated as untrusted to avoid SSRF.
"""

import asyncio
import logging
import re
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit

import httpx

from .config import get_settings
from .models import SubmissionType
from .schemas import GitHubRequirement
from .telemetry import track_dependency


def _get_github_headers() -> dict[str, str]:
    """Get headers for GitHub API requests, including auth token if available."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    settings = get_settings()
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers

logger = logging.getLogger(__name__)


def _is_public_ip(ip_str: str) -> bool:
    """Return True if the IP is publicly routable (not private/loopback/etc)."""
    try:
        ip_obj = ip_address(ip_str)
    except ValueError:
        return False

    # ipaddress.IPv4Address/IPv6Address has helpful predicates.
    # Prefer is_global when available (py3.13), but guard with fallbacks.
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
    # If host is already an IP literal, validate it directly.
    try:
        ip_address(host)
        return _is_public_ip(host)
    except ValueError:
        pass

    def _resolve() -> list[str]:
        # getaddrinfo can return duplicates; normalize.
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

    # Prevent SSRF to internal networks.
    is_public = await _host_resolves_to_public_ip(hostname)
    if not is_public:
        raise ValueError("URL host is not publicly routable")

    # Drop fragments; keep the rest as-is.
    return parts._replace(fragment="").geturl()


# ============ GitHub Requirements Configuration ============

# Define all GitHub requirements by phase
GITHUB_REQUIREMENTS: dict[int, list[GitHubRequirement]] = {
    1: [
        GitHubRequirement(
            id="phase1-profile-readme",
            phase_id=1,
            submission_type=SubmissionType.PROFILE_README,
            name="GitHub Profile README",
            description="Create a GitHub profile README to introduce yourself. This should be in a repo named after your username.",
            example_url="https://github.com/madebygps/madebygps/blob/main/README.md",
        ),
        GitHubRequirement(
            id="phase1-linux-ctfs-fork",
            phase_id=1,
            submission_type=SubmissionType.REPO_FORK,
            name="Linux CTFs Repository Fork",
            description="Fork the Linux CTFs repository to complete the hands-on challenges.",
            example_url="https://github.com/madebygps/linux-ctfs",
            required_repo="learntocloud/linux-ctfs",
        ),
    ],
    2: [
        GitHubRequirement(
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
        GitHubRequirement(
            id="phase3-deployed-journal-api",
            phase_id=3,
            submission_type=SubmissionType.DEPLOYED_APP,
            name="Deployed Learning Journal API",
            description="Deploy your Learning Journal API to the cloud. We'll verify it's running by making a GET request to your /entries endpoint.",
            example_url="https://your-app.azurewebsites.net/entries",
            expected_endpoint="/entries",
        ),
    ],
}


def get_requirements_for_phase(phase_id: int) -> list[GitHubRequirement]:
    """Get all GitHub requirements for a specific phase."""
    return GITHUB_REQUIREMENTS.get(phase_id, [])


def get_requirement_by_id(requirement_id: str) -> GitHubRequirement | None:
    """Get a specific requirement by its ID."""
    for requirements in GITHUB_REQUIREMENTS.values():
        for req in requirements:
            if req.id == requirement_id:
                return req
    return None


# ============ URL Parsing Utilities ============

@dataclass
class ParsedGitHubUrl:
    """Parsed components of a GitHub URL."""
    username: str
    repo_name: str | None = None
    file_path: str | None = None
    is_valid: bool = True
    error: str | None = None


def parse_github_url(url: str) -> ParsedGitHubUrl:
    """
    Parse a GitHub URL and extract components.
    
    Supports:
    - Profile README: https://github.com/username/username/blob/main/README.md
    - Repository: https://github.com/username/repo-name
    - Repository with path: https://github.com/username/repo-name/tree/main/folder
    """
    url = url.strip().rstrip("/")
    
    # Basic validation
    if not url.startswith("https://github.com/"):
        return ParsedGitHubUrl(
            username="",
            is_valid=False,
            error="URL must start with https://github.com/"
        )
    
    # Remove the base URL
    path = url.replace("https://github.com/", "")
    
    # Split into parts
    parts = path.split("/")
    
    if not parts or not parts[0]:
        return ParsedGitHubUrl(
            username="",
            is_valid=False,
            error="Could not extract username from URL"
        )
    
    username = parts[0]
    
    # Validate username format
    if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$", username):
        return ParsedGitHubUrl(
            username=username,
            is_valid=False,
            error="Invalid GitHub username format"
        )
    
    repo_name = parts[1] if len(parts) > 1 else None
    
    # Extract file path if present (after blob/tree/main/etc)
    file_path = None
    if len(parts) > 3 and parts[2] in ("blob", "tree"):
        # Skip the branch name (parts[3]) and get the rest
        if len(parts) > 4:
            file_path = "/".join(parts[4:])
    
    return ParsedGitHubUrl(
        username=username,
        repo_name=repo_name,
        file_path=file_path,
        is_valid=True
    )


# ============ GitHub API Validation ============

@track_dependency("github_url_check", "HTTP")
async def check_github_url_exists(url: str) -> tuple[bool, str]:
    """
    Check if a GitHub URL exists by making a HEAD request.
    
    Returns:
        Tuple of (exists: bool, message: str)
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.head(url)
            
            if response.status_code == 200:
                return True, "URL exists"
            elif response.status_code == 404:
                return False, "URL not found (404)"
            else:
                return False, f"Unexpected status code: {response.status_code}"
                
    except httpx.TimeoutException:
        return False, "Request timed out"
    except httpx.RequestError as e:
        logger.warning(f"Error checking GitHub URL {url}: {e}")
        return False, f"Request error: {str(e)}"


@track_dependency("github_api_fork_check", "HTTP")
async def check_repo_is_fork_of(username: str, repo_name: str, original_repo: str) -> tuple[bool, str]:
    """
    Check if a repository is a fork of the specified original repository.
    
    Args:
        username: The GitHub username
        repo_name: The repository name to check
        original_repo: The original repo in format "owner/repo"
        
    Returns:
        Tuple of (is_fork: bool, message: str)
    """
    api_url = f"https://api.github.com/repos/{username}/{repo_name}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                api_url,
                headers=_get_github_headers(),
            )

            if response.status_code == 404:
                return False, f"Repository {username}/{repo_name} not found"

            if response.status_code != 200:
                return False, f"GitHub API error: {response.status_code}"

            repo_data = response.json()

            # Check if it's a fork
            if not repo_data.get("fork", False):
                return False, "Repository is not a fork"

            # Check if it's forked from the correct repository
            parent = repo_data.get("parent", {})
            parent_full_name = parent.get("full_name", "")

            if parent_full_name.lower() == original_repo.lower():
                return True, f"Verified fork of {original_repo}"
            else:
                return False, f"Repository is forked from {parent_full_name}, not {original_repo}"

    except httpx.TimeoutException:
        return False, "GitHub API request timed out"
    except httpx.RequestError as e:
        logger.warning(f"Error checking fork status: {e}")
        return False, f"Request error: {str(e)}"


@dataclass
class ValidationResult:
    """Result of validating a GitHub submission."""
    is_valid: bool
    message: str
    username_match: bool
    repo_exists: bool


async def validate_profile_readme(
    github_url: str,
    expected_username: str
) -> ValidationResult:
    """
    Validate a GitHub profile README submission.
    
    The URL should be like: https://github.com/username/username/blob/main/README.md
    And the username should match the expected_username (case-insensitive).
    """
    parsed = parse_github_url(github_url)
    
    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False
        )
    
    # Check if username matches (case-insensitive)
    username_match = parsed.username.lower() == expected_username.lower()
    
    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=f"GitHub username '{parsed.username}' does not match your account username '{expected_username}'",
            username_match=False,
            repo_exists=False
        )
    
    # For profile README, repo name should match username
    if parsed.repo_name and parsed.repo_name.lower() != parsed.username.lower():
        return ValidationResult(
            is_valid=False,
            message=f"Profile README must be in a repo named '{parsed.username}', not '{parsed.repo_name}'",
            username_match=True,
            repo_exists=False
        )
    
    # Check if the URL exists
    exists, exists_msg = await check_github_url_exists(github_url)
    
    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find your profile README. {exists_msg}",
            username_match=True,
            repo_exists=False
        )
    
    return ValidationResult(
        is_valid=True,
        message="Profile README validated successfully!",
        username_match=True,
        repo_exists=True
    )


async def validate_repo_fork(
    github_url: str,
    expected_username: str,
    required_repo: str
) -> ValidationResult:
    """
    Validate a repository fork submission.
    
    The URL should be like: https://github.com/username/repo-name
    And the repo should be a fork of the required_repo.
    """
    parsed = parse_github_url(github_url)
    
    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False
        )
    
    # Check if username matches (case-insensitive)
    username_match = parsed.username.lower() == expected_username.lower()
    
    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=f"GitHub username '{parsed.username}' does not match your account username '{expected_username}'",
            username_match=False,
            repo_exists=False
        )
    
    if not parsed.repo_name:
        return ValidationResult(
            is_valid=False,
            message="Could not extract repository name from URL",
            username_match=True,
            repo_exists=False
        )
    
    # Check if the repo is a fork of the required repo
    is_fork, fork_msg = await check_repo_is_fork_of(
        parsed.username,
        parsed.repo_name,
        required_repo
    )
    
    if not is_fork:
        return ValidationResult(
            is_valid=False,
            message=fork_msg,
            username_match=True,
            repo_exists=False
        )
    
    return ValidationResult(
        is_valid=True,
        message=f"Repository fork validated successfully! {fork_msg}",
        username_match=True,
        repo_exists=True
    )


@track_dependency("deployed_app_check", "HTTP")
async def validate_deployed_app(
    app_url: str,
    expected_endpoint: str | None = None
) -> ValidationResult:
    """
    Validate a deployed application by making a GET request.
    
    Args:
        app_url: The base URL of the deployed app (e.g., https://my-app.azurewebsites.net)
        expected_endpoint: Optional endpoint to append (e.g., "/entries")
        
    Returns:
        ValidationResult indicating if the app is accessible
    """
    # Clean up the URL
    app_url = app_url.strip().rstrip("/")
    
    # Build the full URL to check
    if expected_endpoint:
        # Ensure endpoint starts with /
        if not expected_endpoint.startswith("/"):
            expected_endpoint = "/" + expected_endpoint
        check_url = app_url + expected_endpoint
    else:
        check_url = app_url
    
    try:
        # SSRF hardening: validate the URL and follow redirects manually, validating
        # every hop (redirect targets included).
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
                        username_match=True,  # Not applicable for deployed apps
                        repo_exists=True,  # Using this to indicate "app exists"
                    )

                if status_code in (401, 403):
                    # Authentication required - app is running but endpoint is protected
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
            repo_exists=False
        )
    except httpx.ConnectError:
        return ValidationResult(
            is_valid=False,
            message="Could not connect to your app. Check that the URL is correct and the app is deployed.",
            username_match=True,
            repo_exists=False
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
            repo_exists=False
        )


async def validate_submission(
    requirement: GitHubRequirement,
    submitted_url: str,
    expected_username: str | None = None
) -> ValidationResult:
    """
    Validate a submission based on its requirement type.
    
    Args:
        requirement: The requirement being validated
        submitted_url: The URL submitted by the user
        expected_username: The expected GitHub username (required for GitHub-based validations)
    """
    if requirement.submission_type == SubmissionType.PROFILE_README:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for profile README validation",
                username_match=False,
                repo_exists=False
            )
        return await validate_profile_readme(submitted_url, expected_username)
    elif requirement.submission_type == SubmissionType.REPO_FORK:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for repository fork validation",
                username_match=False,
                repo_exists=False
            )
        if not requirement.required_repo:
            return ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=False,
                repo_exists=False
            )
        return await validate_repo_fork(submitted_url, expected_username, requirement.required_repo)
    elif requirement.submission_type == SubmissionType.DEPLOYED_APP:
        return await validate_deployed_app(submitted_url, requirement.expected_endpoint)
    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False
        )
