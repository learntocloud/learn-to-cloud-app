"""Internal operational endpoints."""

import base64
import binascii
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError
from starlette import status

from learn_to_cloud.services.submissions_service import run_submit_smoke_check

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"], include_in_schema=False)

_SMOKE_ROLE = "Smoke.Trigger"
_APP_ID_CLAIMS = {
    "appid",
    "azp",
    "http://schemas.microsoft.com/identity/claims/appid",
}
_ROLE_CLAIMS = {
    "roles",
    "http://schemas.microsoft.com/ws/2008/06/identity/claims/role",
}


class _ClientPrincipalClaim(BaseModel):
    typ: str
    val: str


class _ClientPrincipal(BaseModel):
    auth_typ: str
    claims: list[_ClientPrincipalClaim]
    role_typ: str = ""


def _require_smoke_principal(encoded_principal: str, expected_client_id: str) -> None:
    """Authorize an identity already validated by Container Apps Easy Auth."""
    if not expected_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Smoke-test identity is not configured.",
        )

    try:
        principal_json = base64.b64decode(encoded_principal, validate=True)
        principal = _ClientPrincipal.model_validate_json(principal_json)
    except (binascii.Error, UnicodeDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated principal.",
        ) from exc

    if principal.auth_typ != "aad":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Smoke test requires Microsoft Entra authentication.",
        )

    claims: dict[str, set[str]] = {}
    for claim in principal.claims:
        claims.setdefault(claim.typ, set()).add(claim.val)

    caller_ids = set().union(*(claims.get(name, set()) for name in _APP_ID_CLAIMS))
    if expected_client_id not in caller_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller is not authorized to run smoke tests.",
        )

    role_claims = _ROLE_CLAIMS | ({principal.role_typ} if principal.role_typ else set())
    roles = set().union(*(claims.get(name, set()) for name in role_claims))
    if _SMOKE_ROLE not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller lacks the smoke-test role.",
        )


@router.post("/internal/smoke/verification")
async def smoke_verification(
    request: Request,
    x_ms_client_principal: str | None = Header(
        default=None, alias="X-MS-CLIENT-PRINCIPAL"
    ),
    x_ms_client_principal_id: str | None = Header(
        default=None, alias="X-MS-CLIENT-PRINCIPAL-ID"
    ),
) -> dict[str, str]:
    """Post-deploy smoke check for the verification submit code path.

    Exercises the same database reads and value parsing as a real
    verification submission, without writing anything, so a deploy whose
    code does not match the migrated database schema fails here instead of
    silently returning 500s to real users (see incident #432).

    Container Apps Easy Auth validates the deployment identity before the
    route authorizes its application ID and Smoke.Trigger role.
    """
    smoke_settings = request.app.state.settings.smoke_test

    if x_ms_client_principal and x_ms_client_principal_id:
        _require_smoke_principal(
            x_ms_client_principal,
            smoke_settings.allowed_client_id,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Smoke-test authentication required.",
        )

    try:
        result = await run_submit_smoke_check(request.app.state.session_maker)
    except Exception as exc:
        logger.error(
            "internal.smoke.verification.failed",
            extra={"error.type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification smoke check failed.",
        ) from exc

    logger.info(
        "internal.smoke.verification.ok",
        extra={"verification.requirement.slug": result["requirement_slug"]},
    )
    return {"status": "ok", **result}
