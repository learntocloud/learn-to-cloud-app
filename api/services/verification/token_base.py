"""HMAC token verification for lab challenges (CTF + Networking Lab).

Verifies base64-encoded HMAC-signed tokens from lab environments.
Each lab type is a simple config: required challenge count, display name, etc.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

from core.config import get_settings
from schemas import ValidationResult

logger = logging.getLogger(__name__)


def _derive_secret(instance_id: str) -> str:
    """Derive an instance-specific secret via SHA-256."""
    master_secret = get_settings().labs_verification_secret
    if not get_settings().debug and not master_secret:
        raise RuntimeError("Labs verification secret is not configured")
    data = f"{master_secret}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def _fail(message: str, *, completed: bool = True) -> ValidationResult:
    return ValidationResult(
        is_valid=False, message=message, verification_completed=completed
    )


def verify_lab_token(
    token: str,
    oauth_github_username: str,
    *,
    required_challenges: int,
    challenge_label: str = "challenges",
    display_name: str = "Lab",
    accepted_challenge_types: frozenset[str] = frozenset(),
) -> ValidationResult:
    """Verify a lab completion token.

    Returns a ValidationResult directly (no intermediate types).
    For networking labs, cloud_provider is extracted from challenge_type.
    """
    try:
        # Decode
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
            token_data = json.loads(decoded)
        except (ValueError, json.JSONDecodeError, binascii.Error):
            return _fail("Invalid token format. Could not decode the token.")

        payload: dict[str, Any] | None = token_data.get("payload")
        signature: str | None = token_data.get("signature")

        if (
            not isinstance(payload, dict)
            or not isinstance(signature, str)
            or not signature
        ):
            return _fail(
                "Invalid token structure. Missing or malformed payload/signature."
            )

        # Challenge type check (networking lab only)
        cloud_provider: str | None = None
        if accepted_challenge_types:
            challenge_type = payload.get("challenge") or ""
            if challenge_type not in accepted_challenge_types:
                return _fail(
                    f"Invalid challenge type '{challenge_type}'. "
                    f"Make sure you're submitting a token from the {display_name}."
                )
            cloud_provider = challenge_type.removeprefix("networking-lab-")

        # Username check
        token_username = (payload.get("github_username") or "").lower()
        if token_username != oauth_github_username.lower():
            return _fail(
                f"GitHub username mismatch. Token is for "
                f"'{payload.get('github_username')}', but you signed in "
                f"as '{oauth_github_username}'."
            )

        # Instance ID + HMAC signature
        instance_id = payload.get("instance_id")
        if not instance_id:
            return _fail("Invalid token: missing instance ID.")

        try:
            verification_secret = _derive_secret(instance_id)
            payload_str = json.dumps(payload, separators=(",", ":"))
            expected_sig = hmac.new(
                verification_secret.encode(), payload_str.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return _fail(
                    "Invalid token signature. The token may have been tampered with."
                )
        except RuntimeError:
            logger.exception("token.verification.misconfigured")
            return _fail(
                f"{display_name} verification is not available right now.",
                completed=False,
            )

        # Challenge count
        challenges = payload.get("challenges", 0)
        if challenges != required_challenges:
            return _fail(
                f"Incomplete {challenge_label}: {challenges}/{required_challenges}. "
                f"Complete all {challenge_label} to get a valid token."
            )

        # Timestamp (reject > 1h in the future)
        timestamp = payload.get("timestamp", 0)
        if not isinstance(timestamp, int | float):
            return _fail("Invalid timestamp format in token.")
        if timestamp > datetime.now(UTC).timestamp() + 3600:
            return _fail("Invalid timestamp. The token appears to be from the future.")

        logger.info(
            "token.verification.passed",
            extra={
                "display_name": display_name,
                "github_username": payload.get("github_username"),
                "challenges": challenges,
            },
        )

        return ValidationResult(
            is_valid=True,
            message=f"🎉 Congratulations! You have completed all "
            f"{required_challenges} {challenge_label}!",
            username_match=True,
            verification_completed=True,
            cloud_provider=cloud_provider,
        )

    except Exception:
        logger.exception("token.verification.failed")
        return _fail(
            "Token verification failed. Please try again or contact support.",
            completed=False,
        )


# ── CTF (Phase 1) ────────────────────────────────────────────────────


def verify_ctf_token(token: str, oauth_github_username: str) -> ValidationResult:
    """Verify a Linux CTF completion token (18 challenges)."""
    return verify_lab_token(
        token,
        oauth_github_username,
        required_challenges=18,
        challenge_label="challenges",
        display_name="CTF",
    )


# ── Networking Lab (Phase 2) ─────────────────────────────────────────

ACCEPTED_CHALLENGE_TYPES = frozenset(
    {"networking-lab-azure", "networking-lab-aws", "networking-lab-gcp"}
)

# Used by tests
REQUIRED_CHALLENGES = 4


def verify_networking_token(token: str, oauth_github_username: str) -> ValidationResult:
    """Verify a Networking Lab completion token (4 incidents)."""
    return verify_lab_token(
        token,
        oauth_github_username,
        required_challenges=REQUIRED_CHALLENGES,
        challenge_label="incidents",
        display_name="Networking Lab",
        accepted_challenge_types=ACCEPTED_CHALLENGE_TYPES,
    )
