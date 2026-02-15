"""Certificate download endpoints.

These endpoints serve certificate files (PDF/PNG) for download.
Certificate creation is handled via HTMX routes.
"""

from functools import lru_cache

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from core.auth import OptionalUserId, UserId
from core.config import get_settings
from core.database import DbSessionReadOnly
from core.ratelimit import limiter
from schemas import CertificateData
from services.certificates_service import (
    generate_certificate_pdf,
    generate_certificate_png,
    get_user_certificate,
    verify_certificate,
)

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


@lru_cache(maxsize=1)
def _get_cache_control() -> str:
    """Get appropriate Cache-Control header value based on environment.

    Cached because settings.debug won't change at runtime.
    """
    settings = get_settings()
    if settings.debug:
        return "no-store"
    return "public, max-age=3600"


async def _build_pdf_response(
    certificate: CertificateData,
    *,
    disposition: str = "attachment",
) -> Response:
    """Generate a PDF and wrap it in a Response with proper headers.

    Raises:
        HTTPException: 501 if PDF generation is not available.
    """
    try:
        pdf_content = await generate_certificate_pdf(certificate)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="ltc-certificate-'
                f'{certificate.verification_code}.pdf"'
            ),
            "Cache-Control": _get_cache_control(),
        },
    )


async def _build_png_response(
    certificate: CertificateData,
    *,
    scale: float = 2.0,
    disposition: str = "attachment",
) -> Response:
    """Generate a PNG and wrap it in a Response with proper headers.

    Raises:
        HTTPException: 501 if PNG generation is not available.
    """
    try:
        png_content = await generate_certificate_png(certificate, scale=scale)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    return Response(
        content=png_content,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="ltc-certificate-'
                f'{certificate.verification_code}.png"'
            ),
            "Cache-Control": _get_cache_control(),
        },
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
    db: DbSessionReadOnly,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
) -> Response:
    """Get the PDF for a verified certificate (public endpoint)."""
    certificate = await verify_certificate(db, verification_code)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return await _build_pdf_response(certificate)


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
    db: DbSessionReadOnly,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
    scale: float = Query(2.0, ge=1.0, le=4.0),
) -> Response:
    """Get a PNG image for a verified certificate (public endpoint)."""
    certificate = await verify_certificate(db, verification_code)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return await _build_png_response(certificate, scale=scale)


@router.get(
    "/mine/pdf",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF certificate"},
        401: {"description": "Not authenticated"},
        404: {"description": "Certificate not found"},
        501: {"description": "PDF generation not available"},
    },
    summary="Download your certificate as PDF",
)
@limiter.limit("10/minute")
async def get_certificate_pdf_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSessionReadOnly,
) -> Response:
    """Get the PDF for the authenticated user's certificate."""
    certificate = await get_user_certificate(db, user_id)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return await _build_pdf_response(certificate)


@router.get(
    "/mine/png",
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG certificate image"},
        401: {"description": "Not authenticated"},
        404: {"description": "Certificate not found"},
        501: {"description": "PNG generation not available"},
    },
    summary="Download your certificate as PNG",
)
@limiter.limit("10/minute")
async def get_certificate_png_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSessionReadOnly,
    scale: float = Query(2.0, ge=1.0, le=4.0),
) -> Response:
    """Get a PNG image for the authenticated user's certificate."""
    certificate = await get_user_certificate(db, user_id)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return await _build_png_response(certificate, scale=scale)
