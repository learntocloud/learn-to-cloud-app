"""Internal operational endpoints.

These routes are not part of the user-facing product. They support
deployment and monitoring tooling and are gated by a shared secret so
they are only reachable where that secret is configured.
"""

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from starlette import status

from learn_to_cloud.services.submissions_service import run_submit_smoke_check

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"], include_in_schema=False)

_SMOKE_TOKEN_HEADER = "X-Smoke-Test-Token"


@router.post("/internal/smoke/verification")
async def smoke_verification(
    request: Request,
    x_smoke_test_token: str | None = Header(default=None),
) -> dict[str, str]:
    """Post-deploy smoke check for the verification submit code path.

    Exercises the same database reads and value parsing as a real
    verification submission, without writing anything, so a deploy whose
    code does not match the migrated database schema fails here instead of
    silently returning 500s to real users (see incident #432).

    Returns 200 when the read path runs cleanly. Returns 503 when it does
    not, which fails the post-deploy smoke step in CI. The endpoint is
    disabled (404) unless ``SMOKE_TEST__TOKEN`` is configured, and rejects
    requests (401) whose ``X-Smoke-Test-Token`` header does not match it.
    """
    configured_token = request.app.state.settings.smoke_test.token

    if not configured_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    provided = x_smoke_test_token or ""
    if not hmac.compare_digest(provided, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid smoke-test token.",
        )

    try:
        result = await run_submit_smoke_check(request.app.state.session_maker)
    except Exception as exc:
        logger.exception("internal.smoke.verification.failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Verification smoke check failed: {type(exc).__name__}: {exc}",
        ) from exc

    logger.info(
        "internal.smoke.verification.ok",
        extra={"requirement_slug": result["requirement_slug"]},
    )
    return {"status": "ok", **result}
