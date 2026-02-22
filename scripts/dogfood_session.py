"""Generate a signed Starlette session cookie for local dogfooding.

Outputs JSON with the cookie name, value, domain, and path so that
browser automation or test scripts can inject the session without
going through the GitHub OAuth flow.

Usage:
    cd api && uv run python ../scripts/dogfood_session.py          # auto-detect first user
    cd api && uv run python ../scripts/dogfood_session.py 6733686  # specific user ID

Security:
    Only works with the dev secret key ("dev-secret-key-change-in-production").
    Production rejects this key at startup (see core/config.py validator).
"""

from __future__ import annotations

import json
import os
import sys
from base64 import b64encode

import itsdangerous

SECRET_KEY = "dev-secret-key-change-in-production"


def _load_secret_key() -> str:
    """Load the session secret key from the API's .env file, falling back to the default."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "api", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SESSION_SECRET_KEY"):
                    _, _, value = line.partition("=")
                    value = value.strip().strip("'\"")
                    if value:
                        return value
    return SECRET_KEY


def _get_user_from_db(user_id: int | None = None) -> dict[str, object] | None:
    """Query the local DB for a user. Returns {"id": ..., "github_username": ...} or None."""
    try:
        import sqlalchemy

        # Build a sync URL from the async one in .env
        raw_url = os.environ.get("DATABASE_URL", "")
        if not raw_url:
            # Try loading from .env file in api/ directory
            env_path = os.path.join(os.path.dirname(__file__), "..", "api", ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("DATABASE_URL="):
                            raw_url = line.split("=", 1)[1].strip()
                            break

        if not raw_url:
            return None

        # Convert async driver to sync for this one-off query
        sync_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

        engine = sqlalchemy.create_engine(sync_url)
        with engine.connect() as conn:
            if user_id is not None:
                row = conn.execute(
                    sqlalchemy.text("SELECT id, github_username FROM users WHERE id = :id"),
                    {"id": user_id},
                ).fetchone()
            else:
                row = conn.execute(
                    sqlalchemy.text("SELECT id, github_username FROM users ORDER BY id LIMIT 1")
                ).fetchone()

            if row:
                return {"id": row[0], "github_username": row[1] or "unknown"}
        return None
    except Exception:
        return None


def generate_cookie(user_id: int, github_username: str) -> dict[str, object]:
    secret = _load_secret_key()
    session_data = {
        "user_id": user_id,
        "github_username": github_username,
    }
    signer = itsdangerous.TimestampSigner(secret)
    payload = b64encode(json.dumps(session_data).encode("utf-8"))
    signed = signer.sign(payload).decode("utf-8")
    return {
        "cookie_name": "session",
        "cookie_value": signed,
        "user_id": user_id,
        "domain": "localhost",
        "path": "/",
    }


def main() -> None:
    # Accept optional user ID argument
    requested_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

    # Try to auto-detect from DB
    user = _get_user_from_db(requested_id)

    if user:
        user_id = user["id"]
        username = str(user["github_username"])
    elif requested_id is not None:
        # Use the requested ID even if DB lookup failed
        user_id = requested_id
        username = "unknown"
    else:
        # Fallback: no DB, no arg — use a synthetic user
        user_id = 1
        username = "dogfood-user"
        print(
            "Warning: No users found in DB. Using synthetic user_id=1. "
            "Pass a user ID as argument or seed the DB first.",
            file=sys.stderr,
        )

    result = generate_cookie(user_id, username)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
