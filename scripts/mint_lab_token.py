"""Mint valid lab completion tokens for local dogfooding.

Phase 1 (CTF) and Phase 2 (Networking Lab) requirements expect an HMAC-signed
token that a learner earns by finishing the lab. Locally there is no lab to
finish, so this script signs an equivalent token with the development secret in
``LABS__VERIFICATION_SECRET``.

The signature is derived from that secret, so a token minted here is only ever
valid against a local environment. Production uses a different secret and will
reject anything produced by this script.

Examples:
    uv run python scripts/mint_lab_token.py --lab ctf --username madebygps
    uv run python scripts/mint_lab_token.py --lab networking --provider azure \
        --username madebygps
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
from datetime import UTC, datetime

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.verification.token_base import (
    ACCEPTED_CHALLENGE_TYPES,
    REQUIRED_CHALLENGES as NETWORKING_REQUIRED_CHALLENGES,
)

CTF_REQUIRED_CHALLENGES = 18
LOCAL_DEV_SECRET = "local_dev_secret_at_least_32_chars"


def build_token(
    *,
    secret: str,
    github_username: str,
    instance_id: str,
    challenges: int,
    challenge_type: str | None,
) -> str:
    """Build a base64 token whose signature matches ``verify_lab_token``."""
    payload: dict[str, object] = {
        "github_username": github_username,
        "instance_id": instance_id,
        "challenges": challenges,
        "timestamp": datetime.now(UTC).timestamp(),
    }
    if challenge_type:
        payload["challenge"] = challenge_type

    derived_secret = hashlib.sha256(f"{secret}:{instance_id}".encode()).hexdigest()
    payload_str = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        derived_secret.encode(), payload_str.encode(), hashlib.sha256
    ).hexdigest()

    token_data = {"payload": payload, "signature": signature}
    return base64.b64encode(json.dumps(token_data).encode()).decode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mint a local lab completion token for dogfooding.",
    )
    parser.add_argument(
        "--lab",
        choices=["ctf", "networking"],
        required=True,
        help="Which lab token to mint: ctf (Phase 1) or networking (Phase 2).",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="GitHub username of the signed-in user the token is issued to.",
    )
    parser.add_argument(
        "--provider",
        choices=["azure", "aws", "gcp"],
        default="azure",
        help="Cloud provider for a networking lab token. Default: azure.",
    )
    parser.add_argument(
        "--instance-id",
        default="dogfood-local",
        help="Lab instance identifier the signature is bound to.",
    )
    parser.add_argument(
        "--challenges",
        type=int,
        help=(
            "Override the completed challenge count. Defaults to the number the "
            "verifier requires, which is what a passing token carries."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    secret = get_worker_settings().labs.verification_secret
    if not secret:
        print(
            "LABS__VERIFICATION_SECRET is not set. Copy "
            "apps/verification-functions/local.settings.example.json to "
            "local.settings.json, or export the variable, then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if secret != LOCAL_DEV_SECRET:
        print(
            "Refusing to run: LABS__VERIFICATION_SECRET is not the documented "
            "local development secret. This script must never be pointed at a "
            "real signing secret.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if args.lab == "ctf":
        challenges = args.challenges or CTF_REQUIRED_CHALLENGES
        challenge_type = None
    else:
        challenges = args.challenges or NETWORKING_REQUIRED_CHALLENGES
        challenge_type = f"networking-lab-{args.provider}"
        if challenge_type not in ACCEPTED_CHALLENGE_TYPES:
            print(f"Unsupported challenge type: {challenge_type}", file=sys.stderr)
            raise SystemExit(1)

    token = build_token(
        secret=secret,
        github_username=args.username,
        instance_id=args.instance_id,
        challenges=challenges,
        challenge_type=challenge_type,
    )
    print(token)


if __name__ == "__main__":
    main()
