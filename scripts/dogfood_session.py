"""Issue a real local login session; stdout is a private browser-cookie JSON value."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import sys

from learn_to_cloud.core.session_cookies import AUTH_COOKIE_NAME
from learn_to_cloud.services.sessions_service import issue_session
from learn_to_cloud_shared.core.config import WebSettings, get_web_settings
from learn_to_cloud_shared.models import User
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def validate_local_target(settings: WebSettings) -> None:
    """Refuse nondevelopment and ambiguous/nonloopback database targets."""
    if not settings.is_development:
        raise ValueError("Session generation requires development configuration")
    url = make_url(settings.database.url)
    if url.drivername != "postgresql+asyncpg" or url.query or not url.database:
        raise ValueError("Session generation requires an explicit local PostgreSQL URL")
    host = url.host or ""
    if host != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError(
                "Session generation requires a loopback database"
            ) from None
        if not address.is_loopback or "%" in host:
            raise ValueError("Session generation requires a loopback database")


async def generate_cookie(
    user_id: int | None = None, *, settings: WebSettings | None = None
) -> dict[str, object]:
    settings = settings or get_web_settings()
    validate_local_target(settings)
    engine = create_async_engine(settings.database.url, hide_parameters=True)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db, db.begin():
            query = select(User).where(
                User.id == user_id
                if user_id is not None
                else User.github_username == "madebygps"
            )
            user = await db.scalar(query)
            if user is None:
                raise ValueError("An existing local account is required")
            issued = await issue_session(db, settings.session, user.id)
        return {
            "cookie_name": AUTH_COOKIE_NAME,
            "cookie_value": issued.token,
            "user_id": user.id,
            "domain": "localhost",
            "path": "/",
        }
    finally:
        await engine.dispose()


def main() -> None:
    requested_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    result = asyncio.run(generate_cookie(requested_id))
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
