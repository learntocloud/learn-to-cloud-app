"""Certificate generation and verification endpoints.

Route ordering note: Literal path segments (/verify/, /eligibility/) are defined
before parameterized segments (/{certificate_id}/) to prevent routing conflicts.
"""

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from core.auth import OptionalUserId, UserId
from core.config import get_settings
from core.database import DbSession
from core.ratelimit import limiter
from schemas import (
    CertificateEligibilityResponse,
    CertificateRequest,
    CertificateResponse,
    CertificateVerifyResponse,
    UserCertificatesResponse,
)
from services.certificates_service import (
    CertificateAlreadyExistsError,
    NotEligibleError,
    check_eligibility,
    create_certificate,
    generate_certificate_pdf,
    generate_certificate_png,
    get_certificate_by_id,
    get_user_certificates_with_eligibility,
    verify_certificate,
    verify_certificate_with_message,
)
from services.users_service import ensure_user_exists

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


def _get_cache_control() -> str:
    """Get appropriate Cache-Control header value based on environment."""
    settings = get_settings()
    if settings.environment.lower() == "development":
        return "no-store"
    return "public, max-age=3600"


# --- Collection endpoints ---


@router.post(
    "",
    response_model=CertificateResponse,
    status_code=201,
    responses={
        409: {"description": "Certificate already exists"},
        403: {"description": "User not eligible for certificate"},
    },
)
@limiter.limit("10/minute")
async def generate_certificate_endpoint(
    request: Request,
    body: CertificateRequest,
    user_id: UserId,
    db: DbSession,
) -> CertificateResponse:
    """Generate a completion certificate for eligible users."""
    await ensure_user_exists(db, user_id)

    try:
        result = await create_certificate(
            db=db,
            user_id=user_id,
            certificate_type=body.certificate_type,
            recipient_name=body.recipient_name,
        )
    except CertificateAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="Certificate already issued. Use GET /certificates to retrieve it.",
        )
    except NotEligibleError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e),
        )

    return result.certificate


@router.get(
    "",
    response_model=UserCertificatesResponse,
    responses={401: {"description": "Not authenticated"}},
)
async def get_user_certificates(
    user_id: UserId,
    db: DbSession,
) -> UserCertificatesResponse:
    """Get all certificates for the authenticated user."""
    await ensure_user_exists(db, user_id)

    (
        certificates,
        full_completion_eligible,
    ) = await get_user_certificates_with_eligibility(db, user_id)

    return UserCertificatesResponse(
        certificates=list(certificates),
        full_completion_eligible=full_completion_eligible,
    )


# --- Literal path routes (before parameterized) ---


@router.get(
    "/eligibility/{certificate_type}",
    response_model=CertificateEligibilityResponse,
    responses={
        400: {"description": "Invalid certificate type"},
        401: {"description": "Not authenticated"},
    },
)
async def check_certificate_eligibility(
    certificate_type: str,
    user_id: UserId,
    db: DbSession,
) -> CertificateEligibilityResponse:
    """Check if user is eligible for a specific certificate type."""
    await ensure_user_exists(db, user_id)

    if certificate_type != "full_completion":
        raise HTTPException(
            status_code=400,
            detail=(
                "Only 'full_completion' certificate type is supported. "
                "Phase achievements are tracked via badges."
            ),
        )

    eligibility = await check_eligibility(db, user_id, certificate_type)

    return CertificateEligibilityResponse(
        is_eligible=eligibility.is_eligible,
        certificate_type=certificate_type,
        phases_completed=eligibility.phases_completed,
        total_phases=eligibility.total_phases,
        completion_percentage=round(eligibility.completion_percentage, 1),
        already_issued=eligibility.existing_certificate is not None,
        existing_certificate_id=eligibility.existing_certificate.id
        if eligibility.existing_certificate
        else None,
        message=eligibility.message,
    )


@router.get(
    "/verify/{verification_code}",
    response_model=CertificateVerifyResponse,
    responses={422: {"description": "Validation error - code too short or long"}},
)
async def verify_certificate_endpoint(
    db: DbSession,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
) -> CertificateVerifyResponse:
    """Verify a certificate by its verification code (public endpoint)."""
    result = await verify_certificate_with_message(db, verification_code)

    return CertificateVerifyResponse(
        is_valid=result.is_valid,
        certificate=result.certificate,
        message=result.message,
    )


@router.get(
    "/verify/{verification_code}/pdf",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF certificate"},
        404: {"description": "Certificate not found"},
    },
)
@limiter.limit("10/minute")
async def get_verified_certificate_pdf_endpoint(
    request: Request,
    db: DbSession,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
) -> Response:
    """Get the PDF for a verified certificate (public endpoint)."""
    certificate = await verify_certificate(db, verification_code)

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    pdf_content = await generate_certificate_pdf(certificate)

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ltc-certificate-'
                f'{certificate.verification_code}.pdf"'
            ),
            "Cache-Control": _get_cache_control(),
        },
    )


@router.get(
    "/verify/{verification_code}/png",
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG certificate image"},
        404: {"description": "Certificate not found"},
        501: {"description": "PNG generation not implemented"},
    },
)
@limiter.limit("10/minute")
async def get_verified_certificate_png_endpoint(
    request: Request,
    db: DbSession,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
    scale: float = Query(2.0, ge=1.0, le=4.0),
) -> Response:
    """Get a PNG image for a verified certificate (public endpoint)."""
    certificate = await verify_certificate(db, verification_code)

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    try:
        png_content = await generate_certificate_png(certificate, scale=scale)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    return Response(
        content=png_content,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'inline; filename="ltc-certificate-'
                f'{certificate.verification_code}.png"'
            ),
            "Cache-Control": _get_cache_control(),
        },
    )


# --- Parameterized routes ---


@router.get(
    "/{certificate_id}/pdf",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF certificate"},
        401: {"description": "Not authenticated"},
        404: {"description": "Certificate not found"},
    },
)
@limiter.limit("10/minute")
async def get_certificate_pdf_endpoint(
    request: Request,
    certificate_id: int,
    user_id: UserId,
    db: DbSession,
) -> Response:
    """Get the PDF for a certificate."""
    certificate = await get_certificate_by_id(db, certificate_id, user_id)

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    pdf_content = await generate_certificate_pdf(certificate)

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ltc-certificate-'
                f'{certificate.verification_code}.pdf"'
            ),
            "Cache-Control": _get_cache_control(),
        },
    )


@router.get(
    "/{certificate_id}/png",
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG certificate image"},
        401: {"description": "Not authenticated"},
        404: {"description": "Certificate not found"},
        501: {"description": "PNG generation not implemented"},
    },
)
@limiter.limit("10/minute")
async def get_certificate_png_endpoint(
    request: Request,
    certificate_id: int,
    user_id: UserId,
    db: DbSession,
    scale: float = Query(2.0, ge=1.0, le=4.0),
) -> Response:
    """Get a PNG image for a certificate."""
    certificate = await get_certificate_by_id(db, certificate_id, user_id)

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    try:
        png_content = await generate_certificate_png(certificate, scale=scale)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    return Response(
        content=png_content,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'inline; filename="ltc-certificate-'
                f'{certificate.verification_code}.png"'
            ),
            "Cache-Control": _get_cache_control(),
        },
    )
