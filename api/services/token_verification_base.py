"""Shared HMAC token verification for lab challenges.

Provides the common token decode → validate → verify HMAC flow used by
both the Linux CTF (``ctf_service``) and Networking Lab
(``networking_lab_service``).

Token format (base64-encoded JSON):
    {
        "payload": {
            "github_username": "...",
            "instance_id": "...",
            "challenges": N,
            "timestamp": ...,
            ...
        },
        "signature": "<HMAC-SHA256 hex>"
    }

Shared steps:
1. Base64-decode and JSON-parse
2. Extract ``payload`` / ``signature``
3. Validate ``github_username`` matches the OAuth user
4. Validate ``instance_id`` is present
5. Derive per-instance secret and verify HMAC signature
6. Validate ``timestamp`` is not in the future (> 1 h tolerance)

Lab-specific steps (handled by each service):
- Challenge-type validation (networking only)
- Required challenge count (18 for CTF, 4 for networking)
- Result type construction (CTFVerificationResult vs NetworkingLabVerificationResult)
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret derivation
# ---------------------------------------------------------------------------


def get_master_secret() -> str:
    """Return the master labs verification secret.

    Raises:
        RuntimeError: If secret is not configured in production.
    """
    settings = get_settings()
    secret = settings.labs_verification_secret
    if not settings.debug and not secret:
        raise RuntimeError("Labs verification secret is not configured")
    return secret


def derive_secret(instance_id: str) -> str:
    """Derive an instance-specific secret via SHA-256.

    Formula: ``SHA256("{master_secret}:{instance_id}")``.
    """
    master_secret = get_master_secret()
    data = f"{master_secret}:{instance_id}"
    return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------


class TokenPayload:
    """Intermediate representation of a decoded token.

    Attributes:
        payload: The raw payload dict from the token.
        signature: The HMAC signature string.
        error: If set, the token is invalid and this describes why.
    """

    __slots__ = ("payload", "signature", "error")

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        signature: str | None = None,
        error: str | None = None,
    ):
        self.payload = payload
        self.signature = signature
        self.error = error

    @property
    def is_valid(self) -> bool:
        return self.error is None


def decode_token(token: str) -> TokenPayload:
    """Base64-decode and JSON-parse a lab token.

    Returns a :class:`TokenPayload` with ``error`` set on failure.
    """
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
        token_data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError, binascii.Error):
        return TokenPayload(error="Invalid token format. Could not decode the token.")

    payload = token_data.get("payload")
    signature = token_data.get("signature")

    if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
        return TokenPayload(
            error="Invalid token structure. Missing or malformed payload/signature."
        )

    return TokenPayload(payload=payload, signature=signature)


# ---------------------------------------------------------------------------
# Core verification steps
# ---------------------------------------------------------------------------


def verify_username(payload: dict[str, Any], oauth_github_username: str) -> str | None:
    """Check that the token's ``github_username`` matches the OAuth user.

    Returns an error message on mismatch, or ``None`` on success.
    """
    token_username = (payload.get("github_username") or "").lower()
    if token_username != oauth_github_username.lower():
        return (
            f"GitHub username mismatch. "
            f"Token is for '{payload.get('github_username')}', "
            f"but you signed in as '{oauth_github_username}'."
        )
    return None


def verify_instance_id(payload: dict[str, Any]) -> str | None:
    """Return an error message if ``instance_id`` is missing, else ``None``."""
    if not payload.get("instance_id"):
        return "Invalid token: missing instance ID."
    return None


def verify_signature(
    payload: dict[str, Any], signature: str, instance_id: str
) -> str | None:
    """Verify the HMAC-SHA256 signature of *payload*.

    Returns an error message on failure, or ``None`` on success.

    Raises:
        RuntimeError: If the master secret is not configured.
    """
    verification_secret = derive_secret(instance_id)
    payload_str = json.dumps(payload, separators=(",", ":"))

    expected_sig = hmac.new(
        verification_secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        return "Invalid token signature. The token may have been tampered with."
    return None


def verify_challenge_count(
    payload: dict[str, Any], required: int, label: str = "challenges"
) -> str | None:
    """Return an error if the challenge count doesn't match *required*.

    Args:
        payload: The decoded token payload.
        required: Expected number of completed challenges/incidents.
        label: Noun used in the error message (``"challenges"`` or ``"incidents"``).
    """
    challenges = payload.get("challenges", 0)
    if challenges != required:
        return (
            f"Incomplete {label}: {challenges}/{required}. "
            f"Complete all {label} to get a valid token."
        )
    return None


def verify_timestamp(payload: dict[str, Any]) -> str | None:
    """Return an error if the timestamp is more than 1 hour in the future."""
    timestamp = payload.get("timestamp", 0)
    if not isinstance(timestamp, int | float):
        return "Invalid timestamp format in token."
    now = datetime.now(UTC).timestamp()
    if timestamp > now + 3600:
        return "Invalid timestamp. The token appears to be from the future."
    return None
