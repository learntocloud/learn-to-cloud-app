"""GitHub-specific validation utilities for hands-on verification.

This module handles all GitHub-specific validations including:
- GitHub profile verification
- Profile README verification
- Repository URL verification
- Repository fork verification
- GitHub URL parsing
- GitHub Actions workflow run verification
- Repository file existence checks

For the main hands-on verification orchestration, see hands_on_verification.py
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC

import httpx

from core.config import get_settings
from core.telemetry import track_dependency


def _get_github_headers() -> dict[str, str]:
    """Get headers for GitHub API requests, including auth token if available."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    settings = get_settings()
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


logger = logging.getLogger(__name__)


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
    
    Also handles common URL variations:
    - Missing https:// prefix (auto-prepends)
    - http:// prefix (converts to https://)
    - www.github.com (normalizes)
    """
    url = url.strip().rstrip("/")

    # Normalize common URL variations
    if url.startswith("http://github.com/"):
        url = url.replace("http://", "https://")
    elif url.startswith("http://www.github.com/"):
        url = url.replace("http://www.", "https://")
    elif url.startswith("https://www.github.com/"):
        url = url.replace("https://www.", "https://")
    elif url.startswith("www.github.com/"):
        url = "https://" + url[4:]  # Remove 'www.' and add https://
    elif url.startswith("github.com/"):
        url = "https://" + url

    if not url.startswith("https://github.com/"):
        return ParsedGitHubUrl(
            username="", is_valid=False, error="URL must be a GitHub URL (e.g., https://github.com/username/repo)"
        )

    path = url.replace("https://github.com/", "")

    parts = path.split("/")

    if not parts or not parts[0]:
        return ParsedGitHubUrl(
            username="", is_valid=False, error="Could not extract username from URL"
        )

    username = parts[0]

    if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$", username):
        return ParsedGitHubUrl(
            username=username, is_valid=False, error="Invalid GitHub username format"
        )

    repo_name = parts[1] if len(parts) > 1 else None

    file_path = None
    if len(parts) > 3 and parts[2] in ("blob", "tree"):
        if len(parts) > 4:
            file_path = "/".join(parts[4:])

    return ParsedGitHubUrl(
        username=username, repo_name=repo_name, file_path=file_path, is_valid=True
    )


@dataclass
class ValidationResult:
    """Result of validating a hands-on submission."""

    is_valid: bool
    message: str
    username_match: bool
    repo_exists: bool


@track_dependency("github_url_check", "HTTP")
async def check_github_url_exists(url: str) -> tuple[bool, str]:
    """
    Check if a GitHub URL exists by making a HEAD request.

    Returns:
        Tuple of (exists: bool, message: str)
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=settings.http_timeout
        ) as client:
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
async def check_repo_is_fork_of(
    username: str, repo_name: str, original_repo: str
) -> tuple[bool, str]:
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
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.get(
                api_url,
                headers=_get_github_headers(),
            )

            if response.status_code == 404:
                return False, f"Repository {username}/{repo_name} not found"

            if response.status_code != 200:
                return False, f"GitHub API error: {response.status_code}"

            repo_data = response.json()

            if not repo_data.get("fork", False):
                return False, "Repository is not a fork"

            parent = repo_data.get("parent", {})
            parent_full_name = parent.get("full_name", "")

            if parent_full_name.lower() == original_repo.lower():
                return True, f"Verified fork of {original_repo}"
            else:
                return (
                    False,
                    f"Forked from {parent_full_name}, not {original_repo}",
                )

    except httpx.TimeoutException:
        return False, "GitHub API request timed out"
    except httpx.RequestError as e:
        logger.warning(f"Error checking fork status: {e}")
        return False, f"Request error: {str(e)}"


async def validate_github_profile(
    github_url: str, expected_username: str
) -> ValidationResult:
    """
    Validate a GitHub profile URL submission.

    The URL should be like: https://github.com/username
    And the username should match the expected_username (case-insensitive).
    """
    url = github_url.strip().rstrip("/")

    if not url.startswith("https://github.com/"):
        return ValidationResult(
            is_valid=False,
            message="URL must be a GitHub profile URL (https://github.com/username)",
            username_match=False,
            repo_exists=False,
        )

    path = url.replace("https://github.com/", "")
    parts = path.split("/")
    username = parts[0] if parts else ""

    if not username:
        return ValidationResult(
            is_valid=False,
            message="Could not extract username from URL",
            username_match=False,
            repo_exists=False,
        )

    username_match = username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    profile_url = f"https://github.com/{username}"
    exists, exists_msg = await check_github_url_exists(profile_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find GitHub profile. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    return ValidationResult(
        is_valid=True,
        message=f"GitHub profile verified for @{username}",
        username_match=True,
        repo_exists=True,
    )


async def validate_repo_url(
    github_url: str, expected_username: str
) -> ValidationResult:
    """
    Validate a GitHub repository URL submission.

    The URL should be like: https://github.com/username/repo-name
    And the username should match the expected_username (case-insensitive).
    """
    parsed = parse_github_url(github_url)

    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    repo_url = f"https://github.com/{parsed.username}/{parsed.repo_name}"
    exists, exists_msg = await check_github_url_exists(repo_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find repository. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    return ValidationResult(
        is_valid=True,
        message=f"Repository verified: {parsed.username}/{parsed.repo_name}",
        username_match=True,
        repo_exists=True,
    )


async def validate_profile_readme(
    github_url: str, expected_username: str
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
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    if parsed.repo_name and parsed.repo_name.lower() != parsed.username.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"Profile README must be in a repo named "
                f"'{parsed.username}', not '{parsed.repo_name}'"
            ),
            username_match=True,
            repo_exists=False,
        )

    exists, exists_msg = await check_github_url_exists(github_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find your profile README. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    return ValidationResult(
        is_valid=True,
        message="Profile README validated successfully!",
        username_match=True,
        repo_exists=True,
    )


async def validate_repo_fork(
    github_url: str, expected_username: str, required_repo: str
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
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    if not parsed.repo_name:
        return ValidationResult(
            is_valid=False,
            message="Could not extract repository name from URL",
            username_match=True,
            repo_exists=False,
        )

    is_fork, fork_msg = await check_repo_is_fork_of(
        parsed.username, parsed.repo_name, required_repo
    )

    if not is_fork:
        return ValidationResult(
            is_valid=False, message=fork_msg, username_match=True, repo_exists=False
        )

    return ValidationResult(
        is_valid=True,
        message=f"Repository fork validated successfully! {fork_msg}",
        username_match=True,
        repo_exists=True,
    )


@track_dependency("github_api_workflow_runs", "HTTP")
async def validate_workflow_run(
    github_url: str, expected_username: str, min_successful_runs: int = 1
) -> ValidationResult:
    """
    Validate that a repository has successful GitHub Actions workflow runs.

    Checks the GitHub API for workflow runs that completed successfully
    within the last 30 days.

    Args:
        github_url: The repository URL
        expected_username: Expected GitHub username
        min_successful_runs: Minimum number of successful runs required (default: 1)

    Returns:
        ValidationResult with details about the workflow run status
    """
    parsed = parse_github_url(github_url)

    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    if not parsed.repo_name:
        return ValidationResult(
            is_valid=False,
            message="Could not extract repository name from URL",
            username_match=True,
            repo_exists=False,
        )

    # Check if repo exists first
    repo_url = f"https://github.com/{parsed.username}/{parsed.repo_name}"
    exists, exists_msg = await check_github_url_exists(repo_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find repository. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    # Check GitHub Actions workflow runs
    api_url = f"https://api.github.com/repos/{parsed.username}/{parsed.repo_name}/actions/runs"
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.get(
                api_url,
                headers=_get_github_headers(),
                params={"status": "success", "per_page": 10},
            )

            if response.status_code == 404:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        "GitHub Actions not found. Make sure Actions is enabled "
                        "and you have at least one workflow file in .github/workflows/"
                    ),
                    username_match=True,
                    repo_exists=True,
                )

            if response.status_code != 200:
                return ValidationResult(
                    is_valid=False,
                    message=f"GitHub API error: {response.status_code}",
                    username_match=True,
                    repo_exists=True,
                )

            data = response.json()
            total_count = data.get("total_count", 0)
            runs = data.get("workflow_runs", [])

            if total_count == 0 or len(runs) == 0:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        "No successful workflow runs found. Run your CI/CD pipeline "
                        "at least once and make sure it passes!"
                    ),
                    username_match=True,
                    repo_exists=True,
                )

            # Check for recent runs (within last 30 days)
            from datetime import datetime, timedelta

            cutoff_date = datetime.now(UTC) - timedelta(days=30)
            recent_successful_runs = []

            for run in runs:
                run_date_str = run.get("created_at", "")
                if run_date_str:
                    try:
                        run_date = datetime.fromisoformat(
                            run_date_str.replace("Z", "+00:00")
                        )
                        if run_date >= cutoff_date:
                            recent_successful_runs.append(run)
                    except ValueError:
                        continue

            if len(recent_successful_runs) < min_successful_runs:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Found {len(recent_successful_runs)} successful runs in "
                        f"the last 30 days, but {min_successful_runs} required. "
                        "Run your pipeline again!"
                    ),
                    username_match=True,
                    repo_exists=True,
                )

            # Get the most recent run info for the success message
            latest_run = recent_successful_runs[0]
            workflow_name = latest_run.get("name", "workflow")

            return ValidationResult(
                is_valid=True,
                message=(
                    f"CI/CD verified! Found {len(recent_successful_runs)} "
                    f"successful run(s) of '{workflow_name}' in the last 30 days."
                ),
                username_match=True,
                repo_exists=True,
            )

    except httpx.TimeoutException:
        return ValidationResult(
            is_valid=False,
            message="GitHub API request timed out. Please try again.",
            username_match=True,
            repo_exists=True,
        )
    except httpx.RequestError as e:
        logger.warning(f"Error checking workflow runs: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Request error: {str(e)}",
            username_match=True,
            repo_exists=True,
        )


@track_dependency("github_api_file_search", "HTTP")
async def validate_repo_has_files(
    github_url: str,
    expected_username: str,
    required_patterns: list[str],
    file_description: str,
) -> ValidationResult:
    """
    Validate that a repository contains files matching specified patterns.

    Uses GitHub's search API to look for files in the repository.

    Args:
        github_url: The repository URL
        expected_username: Expected GitHub username
        required_patterns: List of file patterns to search for
            (e.g., ["Dockerfile", "docker-compose"])
        file_description: Human-readable description of what we're looking for

    Returns:
        ValidationResult with details about the file search
    """
    parsed = parse_github_url(github_url)

    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    if not parsed.repo_name:
        return ValidationResult(
            is_valid=False,
            message="Could not extract repository name from URL",
            username_match=True,
            repo_exists=False,
        )

    # Check if repo exists first
    repo_url = f"https://github.com/{parsed.username}/{parsed.repo_name}"
    exists, exists_msg = await check_github_url_exists(repo_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find repository. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    # Use GitHub's code search API to find files
    settings = get_settings()
    found_files = []

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            for pattern in required_patterns:
                # Search for files matching the pattern in the repo
                search_query = (
                    f"filename:{pattern} repo:{parsed.username}/{parsed.repo_name}"
                )
                api_url = "https://api.github.com/search/code"

                response = await client.get(
                    api_url,
                    headers=_get_github_headers(),
                    params={"q": search_query, "per_page": 5},
                )

                # Handle rate limiting
                if response.status_code == 403:
                    # Try alternative: check repo contents directly
                    return await _validate_repo_files_via_contents(
                        client,
                        parsed.username,
                        parsed.repo_name,
                        required_patterns,
                        file_description,
                    )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("total_count", 0) > 0:
                        items = data.get("items", [])
                        for item in items:
                            found_files.append(item.get("name", pattern))

            if not found_files:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Could not find {file_description} in your repository. "
                        f"Make sure you have files like: {', '.join(required_patterns)}"
                    ),
                    username_match=True,
                    repo_exists=True,
                )

            return ValidationResult(
                is_valid=True,
                message=f"Found {file_description}: {', '.join(set(found_files))}",
                username_match=True,
                repo_exists=True,
            )

    except httpx.TimeoutException:
        return ValidationResult(
            is_valid=False,
            message="GitHub API request timed out. Please try again.",
            username_match=True,
            repo_exists=True,
        )
    except httpx.RequestError as e:
        logger.warning(f"Error searching for files: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Request error: {str(e)}",
            username_match=True,
            repo_exists=True,
        )


async def _validate_repo_files_via_contents(
    client: httpx.AsyncClient,
    username: str,
    repo_name: str,
    required_patterns: list[str],
    file_description: str,
) -> ValidationResult:
    """
    Fallback validation using repo contents API when search is rate-limited.

    Checks root directory and common subdirectories for matching files.
    """
    found_files = []
    directories_to_check = [
        "",
        "infra",
        "terraform",
        "k8s",
        "kubernetes",
        "manifests",
        ".github/workflows",
    ]

    for directory in directories_to_check:
        path = f"/{directory}" if directory else ""
        api_url = f"https://api.github.com/repos/{username}/{repo_name}/contents{path}"

        try:
            response = await client.get(
                api_url,
                headers=_get_github_headers(),
            )

            if response.status_code != 200:
                continue

            contents = response.json()
            if not isinstance(contents, list):
                continue

            for item in contents:
                item_name = item.get("name", "").lower()
                for pattern in required_patterns:
                    pattern_lower = pattern.lower()
                    # Check if filename matches pattern (partial match)
                    if pattern_lower in item_name or item_name.startswith(
                        pattern_lower
                    ):
                        found_files.append(item.get("name", pattern))

        except (httpx.RequestError, ValueError):
            continue

    if not found_files:
        return ValidationResult(
            is_valid=False,
            message=(
                f"Could not find {file_description} in your repository. "
                f"Make sure you have files like: {', '.join(required_patterns)}"
            ),
            username_match=True,
            repo_exists=True,
        )

    return ValidationResult(
        is_valid=True,
        message=f"Found {file_description}: {', '.join(set(found_files))}",
        username_match=True,
        repo_exists=True,
    )


async def validate_container_image(
    image_url: str,
    expected_username: str,
) -> ValidationResult:
    """
    Validate that a container image exists and is publicly accessible.

    Supports:
    - Docker Hub: username/image or docker.io/username/image
    - GitHub Container Registry: ghcr.io/username/image
    - Azure Container Registry: *.azurecr.io/image

    Args:
        image_url: The container image URL/reference
        expected_username: Expected username (for ownership verification)

    Returns:
        ValidationResult with details about the image
    """
    image_url = image_url.strip().lower()

    # Remove common prefixes
    if image_url.startswith("https://"):
        image_url = image_url[8:]
    if image_url.startswith("http://"):
        image_url = image_url[7:]

    settings = get_settings()

    # Parse the image reference
    # Docker Hub format: username/image:tag or docker.io/username/image:tag
    # GHCR format: ghcr.io/username/image:tag
    # ACR format: registryname.azurecr.io/image:tag

    registry = "docker.io"
    image_path = image_url
    tag = "latest"

    # Extract tag if present
    if ":" in image_path and "@" not in image_path:
        image_path, tag = image_path.rsplit(":", 1)

    # Determine registry
    if image_path.startswith("ghcr.io/"):
        registry = "ghcr.io"
        image_path = image_path[8:]  # Remove "ghcr.io/"
    elif image_path.startswith("docker.io/"):
        registry = "docker.io"
        image_path = image_path[10:]  # Remove "docker.io/"
    elif ".azurecr.io/" in image_path:
        # Azure Container Registry
        parts = image_path.split("/", 1)
        registry = parts[0]
        image_path = parts[1] if len(parts) > 1 else ""

    # Validate image path has at least username/image format for Docker Hub and GHCR
    if registry in ["docker.io", "ghcr.io"]:
        if "/" not in image_path:
            # Docker Hub library images (e.g., "python") - add library prefix
            if registry == "docker.io":
                image_path = f"library/{image_path}"
            else:
                return ValidationResult(
                    is_valid=False,
                    message="GHCR images must be in format: ghcr.io/username/image",
                    username_match=False,
                    repo_exists=False,
                )

        # Check username match for Docker Hub and GHCR
        image_username = image_path.split("/")[0]
        if image_username != "library":  # Skip check for official Docker images
            username_match = image_username == expected_username.lower()
            if not username_match:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Image owner '{image_username}' does not match "
                        f"your username '{expected_username}'"
                    ),
                    username_match=False,
                    repo_exists=False,
                )

    # Common Accept header for Docker manifest requests
    accept_header = (
        "application/vnd.docker.distribution.manifest.v2+json,"
        "application/vnd.oci.image.manifest.v1+json"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            # Check if image exists by querying the registry API
            if registry == "docker.io":
                # Docker Hub API v2
                # First get a token for the repository
                token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{image_path}:pull"
                token_resp = await client.get(token_url)

                if token_resp.status_code != 200:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            "Could not authenticate with Docker Hub "
                            f"for image '{image_path}'"
                        ),
                        username_match=True,
                        repo_exists=False,
                    )

                token = token_resp.json().get("token", "")

                # Check if the manifest exists
                manifest_url = (
                    f"https://registry-1.docker.io/v2/{image_path}/manifests/{tag}"
                )
                manifest_resp = await client.get(
                    manifest_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": accept_header,
                    },
                )

                if manifest_resp.status_code == 200:
                    return ValidationResult(
                        is_valid=True,
                        message=f"Found public Docker Hub image: {image_path}:{tag}",
                        username_match=True,
                        repo_exists=True,
                    )
                elif manifest_resp.status_code == 404:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            f"Image '{image_path}:{tag}' not found on Docker Hub. "
                            "Make sure it's pushed and public."
                        ),
                        username_match=True,
                        repo_exists=False,
                    )
                else:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            "Could not verify image. Docker Hub returned "
                            f"status {manifest_resp.status_code}"
                        ),
                        username_match=True,
                        repo_exists=False,
                    )

            elif registry == "ghcr.io":
                # GitHub Container Registry - check via GitHub API
                # GHCR images are linked to GitHub repos/users
                ghcr_api_url = f"https://ghcr.io/v2/{image_path}/manifests/{tag}"

                # Try anonymous access first (public images)
                manifest_resp = await client.get(
                    ghcr_api_url,
                    headers={
                        "Accept": accept_header,
                    },
                )

                if manifest_resp.status_code == 200:
                    return ValidationResult(
                        is_valid=True,
                        message=f"Found public GHCR image: ghcr.io/{image_path}:{tag}",
                        username_match=True,
                        repo_exists=True,
                    )
                elif manifest_resp.status_code in [401, 403]:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            f"Image 'ghcr.io/{image_path}' exists but is not public. "
                            "Please make it public in your GitHub package settings."
                        ),
                        username_match=True,
                        repo_exists=True,
                    )
                elif manifest_resp.status_code == 404:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            f"Image 'ghcr.io/{image_path}:{tag}' not found. "
                            "Make sure it's pushed to GHCR."
                        ),
                        username_match=True,
                        repo_exists=False,
                    )
                else:
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            "Could not verify GHCR image. "
                            f"Status: {manifest_resp.status_code}"
                        ),
                        username_match=True,
                        repo_exists=False,
                    )

            elif ".azurecr.io" in registry:
                # Azure Container Registry - we can't easily verify without credentials
                # Just validate the format and inform the user
                return ValidationResult(
                    is_valid=True,
                    message=(
                        f"ACR image reference accepted: "
                        f"{registry}/{image_path}:{tag}. "
                        "Note: We cannot verify ACR images "
                        "are public without credentials."
                    ),
                    username_match=True,
                    repo_exists=True,
                )

            else:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Unsupported container registry: {registry}. "
                        "Please use Docker Hub, GHCR, or Azure ACR."
                    ),
                    username_match=False,
                    repo_exists=False,
                )

    except httpx.TimeoutException:
        return ValidationResult(
            is_valid=False,
            message="Container registry request timed out. Please try again.",
            username_match=True,
            repo_exists=False,
        )
    except httpx.RequestError as e:
        logger.warning(f"Error checking container image: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Request error: {str(e)}",
            username_match=True,
            repo_exists=False,
        )
