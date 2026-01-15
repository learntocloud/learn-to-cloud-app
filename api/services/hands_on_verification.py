"""Hands-on verification orchestration module.

This module provides the central orchestration for all hands-on verification:
- Routes submissions to appropriate validators
- Contains validation functions for deployed apps and Journal API responses

Phase requirements are defined in phase_requirements.py.

EXTENSIBILITY:
To add a new verification type:
1. Add the SubmissionType enum value in models.py
2. Add optional fields to HandsOnRequirement in schemas.py if needed
3. Create a validator function (here or in a new module):
   - async def validate_<type>(url: str, ...) -> ValidationResult
4. Add routing case in validate_submission() below

For GitHub-specific validations, see github_hands_on_verification.py
For CTF token validation, see ctf.py
For phase requirements, see phase_requirements.py
"""

import asyncio
import logging
import socket
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit

import httpx

from core.telemetry import track_dependency
from models import SubmissionType
from schemas import HandsOnRequirement

from .ctf import verify_ctf_token
from .github_hands_on_verification import (
    ValidationResult,
    validate_container_image,
    validate_github_profile,
    validate_profile_readme,
    validate_repo_fork,
    validate_repo_has_files,
    validate_repo_url,
    validate_workflow_run,
)
from .phase_requirements import (
    HANDS_ON_REQUIREMENTS,
    get_requirement_by_id,
    get_requirements_for_phase,
)

# Re-export for backwards compatibility
__all__ = [
    "HANDS_ON_REQUIREMENTS",
    "get_requirement_by_id",
    "get_requirements_for_phase",
    "validate_submission",
    "validate_deployed_app",
    "validate_journal_api_response",
    "ValidationResult",
]

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
                addrs.add(str(sockaddr[0]))
            elif family == socket.AF_INET6:
                addrs.add(str(sockaddr[0]))
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


def validate_journal_api_response(response_text: str) -> ValidationResult:
    """
    Validate a Journal API GET /entries response.

    Checks that the response is valid JSON with the expected structure:
    - Must be a JSON array
    - Must contain at least one entry
    - Each entry must have: id, work, struggle, intention, created_at

    Args:
        response_text: The JSON response text pasted by the user

    Returns:
        ValidationResult indicating if the response is valid
    """
    import json
    import re

    response_text = response_text.strip()

    if not response_text:
        return ValidationResult(
            is_valid=False,
            message="Please paste your GET /entries JSON response.",
            username_match=True,
            repo_exists=False,
        )

    # Try to parse as JSON
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        return ValidationResult(
            is_valid=False,
            message=(
                "Invalid JSON format. Make sure you copied the entire "
                f"response. Error: {e.msg}"
            ),
            username_match=True,
            repo_exists=False,
        )

    # Handle both formats:
    # 1. Wrapped response: {"entries": [...], "count": N}
    # 2. Raw array: [...]
    entries: list
    if isinstance(data, dict) and "entries" in data:
        entries = data["entries"]
        if not isinstance(entries, list):
            return ValidationResult(
                is_valid=False,
                message="The 'entries' field should be a list.",
                username_match=True,
                repo_exists=False,
            )
    elif isinstance(data, list):
        entries = data
    else:
        return ValidationResult(
            is_valid=False,
            message=(
                "Response should be a JSON array or an object with "
                "'entries' key. Did you call GET /entries?"
            ),
            username_match=True,
            repo_exists=False,
        )

    # Must have at least one entry
    if len(entries) == 0:
        return ValidationResult(
            is_valid=False,
            message=(
                "No entries found. Create at least one journal entry "
                "using POST /entries first, then try GET /entries again."
            ),
            username_match=True,
            repo_exists=False,
        )

    # Validate each entry has required fields
    required_fields = ["id", "work", "struggle", "intention", "created_at"]
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return ValidationResult(
                is_valid=False,
                message=f"Entry {i + 1} is not a valid object.",
                username_match=True,
                repo_exists=False,
            )

        missing_fields = [f for f in required_fields if f not in entry]
        if missing_fields:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Entry {i + 1} is missing required fields: "
                    f"{', '.join(missing_fields)}. Make sure your Entry "
                    "model has all the required fields."
                ),
                username_match=True,
                repo_exists=False,
            )

        # Validate UUID format for id
        entry_id = entry.get("id", "")
        if not uuid_pattern.match(str(entry_id)):
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Entry {i + 1} has an invalid ID format. Expected "
                    "UUID format (e.g., 123e4567-e89b-12d3-a456-426614174000)."
                ),
                username_match=True,
                repo_exists=False,
            )

        # Validate work, struggle, intention are non-empty strings
        for field in ["work", "struggle", "intention"]:
            value = entry.get(field, "")
            if not isinstance(value, str) or not value.strip():
                return ValidationResult(
                    is_valid=False,
                    message=f"Entry {i + 1} has an empty or invalid '{field}' field.",
                    username_match=True,
                    repo_exists=False,
                )

    entry_count = len(entries)
    entry_word = "entry" if entry_count == 1 else "entries"
    return ValidationResult(
        is_valid=True,
        message=(
            f"Verified! Your Journal API is working correctly "
            f"with {entry_count} {entry_word}. 🎉"
        ),
        username_match=True,
        repo_exists=True,
    )


def _validate_deployed_journal_response(
    response_text: str, url: str
) -> ValidationResult:
    """
    Validate a deployed Journal API response.

    This is used for Phase 4 verification where we call the user's deployed API
    and validate the response structure matches the expected Journal API format.

    Args:
        response_text: The response body from the deployed API
        url: The URL that was called (for error messages)

    Returns:
        ValidationResult with deployment-specific messaging
    """
    import json

    # Try to parse as JSON first
    try:
        json.loads(response_text)  # Validate JSON is parseable
    except json.JSONDecodeError:
        return ValidationResult(
            is_valid=False,
            message=(
                "Your API returned a response but it's not valid JSON. "
                "Make sure your /entries endpoint returns JSON."
            ),
            username_match=True,
            repo_exists=True,
        )

    # Use the same validation logic as the local validator
    result = validate_journal_api_response(response_text)

    if result.is_valid:
        # Customize success message for deployed app
        return ValidationResult(
            is_valid=True,
            message=f"Your deployed Journal API is working! {result.message}",
            username_match=True,
            repo_exists=True,
        )

    # Customize error messages for deployment context
    error_msg = result.message

    # Add deployment-specific hints
    if "No entries found" in error_msg:
        return ValidationResult(
            is_valid=False,
            message=(
                "Your API is running but has no journal entries. "
                "Create at least one entry using POST /entries on your deployed app, "
                "then try verification again."
            ),
            username_match=True,
            repo_exists=True,
        )

    if "missing required fields" in error_msg:
        return ValidationResult(
            is_valid=False,
            message=(
                f"Your API returned entries but they're missing fields. {error_msg} "
                "Check your Entry model matches the expected schema."
            ),
            username_match=True,
            repo_exists=True,
        )

    if "invalid ID format" in error_msg:
        return ValidationResult(
            is_valid=False,
            message=(
                f"{error_msg} Make sure your Entry model generates "
                "UUIDs for the id field."
            ),
            username_match=True,
            repo_exists=True,
        )

    # Return the original error with deployment context
    return ValidationResult(
        is_valid=False,
        message=f"API response validation failed: {error_msg}",
        username_match=True,
        repo_exists=True,
    )


@track_dependency("deployed_app_check", "HTTP")
async def validate_deployed_app(
    app_url: str,
    expected_endpoint: str | None = None,
    validate_journal_response: bool = False,
) -> ValidationResult:
    """
    Validate a deployed application by making a GET request.

    Args:
        app_url: The base URL of the deployed app
            (e.g., https://my-app.azurewebsites.net)
        expected_endpoint: Optional endpoint to append (e.g., "/entries")
        validate_journal_response: If True, also validate the response is a
            valid Journal API

    Returns:
        ValidationResult indicating if the app is accessible and valid
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

                response = await client.get(safe_url)
                status_code = response.status_code
                location = response.headers.get("location")

                if status_code in (301, 302, 303, 307, 308):
                    if not location:
                        return ValidationResult(
                            is_valid=False,
                            message=(
                                "App returned a redirect without a Location header."
                            ),
                            username_match=True,
                            repo_exists=False,
                        )
                    current_url = urljoin(safe_url, location)
                    continue

                if status_code == 200:
                    # If we need to validate the Journal API response
                    if validate_journal_response:
                        return _validate_deployed_journal_response(
                            response.text, safe_url
                        )

                    return ValidationResult(
                        is_valid=True,
                        message=f"App is live! Successfully reached {safe_url}",
                        username_match=True,
                        repo_exists=True,
                    )

                if status_code in (401, 403):
                    endpoint = expected_endpoint or "/"
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            f"App is running but {endpoint} requires "
                            "authentication. Make sure the endpoint is "
                            "publicly accessible without auth."
                        ),
                        username_match=True,
                        repo_exists=True,
                    )

                if status_code == 404:
                    endpoint = expected_endpoint or "/"
                    return ValidationResult(
                        is_valid=False,
                        message=(
                            "Endpoint not found (404). Make sure your app "
                            f"has a {endpoint} endpoint."
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
            message=(
                "Request timed out. Is your app running and "
                "accessible from the internet?"
            ),
            username_match=True,
            repo_exists=False,
        )
    except httpx.ConnectError:
        return ValidationResult(
            is_valid=False,
            message=(
                "Could not connect to your app. Check that the URL is "
                "correct and the app is deployed."
            ),
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
        submitted_value: The value submitted by the user
            (URL, token, or challenge response)
        expected_username: The expected GitHub username
            (required for GitHub-based validations)
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
        return await validate_deployed_app(
            submitted_value,
            requirement.expected_endpoint,
            validate_journal_response=requirement.validate_response_body,
        )

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

    elif requirement.submission_type == SubmissionType.JOURNAL_API_RESPONSE:
        return validate_journal_api_response(submitted_value)

    elif requirement.submission_type == SubmissionType.WORKFLOW_RUN:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for workflow run validation",
                username_match=False,
                repo_exists=False,
            )
        return await validate_workflow_run(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.REPO_WITH_FILES:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for repository file validation",
                username_match=False,
                repo_exists=False,
            )
        if not requirement.required_file_patterns:
            return ValidationResult(
                is_valid=False,
                message=(
                    "Requirement configuration error: missing required_file_patterns"
                ),
                username_match=False,
                repo_exists=False,
            )
        return await validate_repo_has_files(
            submitted_value,
            expected_username,
            requirement.required_file_patterns,
            requirement.file_description or "required files",
        )

    elif requirement.submission_type == SubmissionType.CONTAINER_IMAGE:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message=(
                    "GitHub/Docker username is required for container image validation"
                ),
                username_match=False,
                repo_exists=False,
            )
        return await validate_container_image(submitted_value, expected_username)

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )
