"""Separate browser authentication credentials from signed OAuth state."""

import base64
import hashlib
import re
from datetime import UTC, datetime

from fastapi import Request, Response
from learn_to_cloud_shared.core.config import get_web_settings
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

AUTH_COOKIE_NAME = "ltc_session"
SESSION_COOKIE_NAME = "session"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)


def token_digest(value: str | None) -> bytes | None:
    """Reject noncanonical credentials before contacting the database."""
    if value is None or _TOKEN.fullmatch(value) is None:
        return None
    raw = base64.urlsafe_b64decode(value + "=")
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != value:
        return None
    return hashlib.sha256(raw).digest()


def clear_cookies(request: Request) -> None:
    request.session.clear()
    request.state.clear_auth_cookie = True
    request.state.clear_oauth_cookie = True


def issue_cookie(
    request: Request, response: Response, token: str, expires_at: datetime
) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max(0, int((expires_at - datetime.now(UTC)).total_seconds())),
        expires=expires_at,
        path="/",
        secure=get_web_settings().web_security.require_https,
        httponly=True,
        samesite="lax",
    )
    request.state.auth_cookie_issued = True


class SessionResponseMiddleware:
    """Apply lifecycle headers even to handled authentication failures."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                state = scope.get("state", {})
                headers = MutableHeaders(scope=message)
                auth_route = scope["path"].startswith("/auth/")
                if state.get("auth_resolved") or auth_route:
                    vary = headers.get("vary", "")
                    if "cookie" not in {v.strip().lower() for v in vary.split(",")}:
                        headers["vary"] = f"{vary}, Cookie" if vary else "Cookie"
                    headers["cache-control"] = "private, no-store"
                cleanup = Response()
                names = []
                if state.get("clear_auth_cookie") and not state.get(
                    "auth_cookie_issued"
                ):
                    names.append(AUTH_COOKIE_NAME)
                if state.get("clear_oauth_cookie"):
                    names.append(SESSION_COOKIE_NAME)
                for name in names:
                    cleanup.delete_cookie(
                        name,
                        path="/",
                        secure=get_web_settings().web_security.require_https,
                        httponly=True,
                        samesite="lax",
                    )
                for key, value in cleanup.raw_headers:
                    if key == b"set-cookie":
                        headers.append("set-cookie", value.decode("latin-1"))
            await send(message)

        await self.app(scope, receive, send_response)
