"""Certificate generation and verification endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Path, Response
from sqlalchemy import select

from shared.auth import OptionalUserId, UserId
from shared.certificates import (
    PHASE_TOPIC_COUNTS,
    generate_certificate_svg,
    generate_verification_code,
    get_certificate_info,
    get_completion_requirements,
    svg_to_pdf,
)
from shared.config import get_settings
from shared.database import DbSession
from shared.models import (
    ActivityType,
    Certificate,
    ChecklistProgress,
    UserActivity,
)
from shared.schemas import (
    CertificateEligibilityResponse,
    CertificateRequest,
    CertificateResponse,
    CertificateVerifyResponse,
    UserCertificatesResponse,
)

from .users import get_or_create_user

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


async def _count_completed_topics(
    db: DbSession,
    user_id: str,
    phase_ids: list[int] | None = None,
) -> dict[int, int]:
    """Count completed topics per phase for a user.

    A topic is considered complete when all its checklist items are completed.
    Returns dict mapping phase_id -> completed_topic_count.
    """
    # Get all completed checklist items for the user
    query = select(ChecklistProgress).where(
        ChecklistProgress.user_id == user_id,
        ChecklistProgress.is_completed.is_(True),
    )
    if phase_ids:
        query = query.where(ChecklistProgress.phase_id.in_(phase_ids))

    result = await db.execute(query)
    progress_items = result.scalars().all()

    # Group completed items by phase and topic
    # Item IDs are like "phase0-topic1-check1" or "phase0-check1"
    completed_by_phase: dict[int, set[str]] = {}
    for item in progress_items:
        phase_id = item.phase_id
        item_id = item.checklist_item_id

        if phase_id not in completed_by_phase:
            completed_by_phase[phase_id] = set()

        # Extract topic identifier if present
        parts = item_id.split("-")
        if len(parts) >= 2:
            # Track unique topic completions
            topic_id = f"{parts[0]}-{parts[1]}" if len(parts) > 2 else item_id
            completed_by_phase[phase_id].add(topic_id)

    # For simplicity, estimate topic completion based on checklist items
    # A more accurate approach would track specific topic IDs
    topic_counts: dict[int, int] = {}
    for phase_id in range(6):
        if phase_ids and phase_id not in phase_ids:
            continue
        completed_items = len(completed_by_phase.get(phase_id, set()))
        total_items = PHASE_TOPIC_COUNTS.get(phase_id, 0)
        # Estimate completed topics based on progress ratio
        if total_items > 0:
            topic_counts[phase_id] = min(
                completed_items,
                total_items,
            )
        else:
            topic_counts[phase_id] = 0

    return topic_counts


async def _check_eligibility(
    db: DbSession,
    user_id: str,
    certificate_type: str,
) -> tuple[bool, int, int, float, Certificate | None]:
    """Check if user is eligible for a certificate.

    Returns (is_eligible, topics_completed, total_topics, percentage, existing_cert).
    """
    requirements = get_completion_requirements(certificate_type)
    required_phases = requirements["required_phases"]
    min_percentage = requirements["min_completion_percentage"]

    # Check if certificate already exists
    result = await db.execute(
        select(Certificate).where(
            Certificate.user_id == user_id,
            Certificate.certificate_type == certificate_type,
        )
    )
    existing_cert = result.scalar_one_or_none()

    # Count completed topics
    topic_counts = await _count_completed_topics(db, user_id, required_phases)

    topics_completed = sum(topic_counts.values())
    total_topics = sum(PHASE_TOPIC_COUNTS.get(p, 0) for p in required_phases)

    if total_topics == 0:
        percentage = 0.0
    else:
        percentage = (topics_completed / total_topics) * 100

    is_eligible = percentage >= min_percentage

    return is_eligible, topics_completed, total_topics, percentage, existing_cert


@router.get(
    "/eligibility/{certificate_type}",
    response_model=CertificateEligibilityResponse,
)
async def check_certificate_eligibility(
    certificate_type: str,
    user_id: UserId,
    db: DbSession,
) -> CertificateEligibilityResponse:
    """Check if user is eligible for a specific certificate type."""
    await get_or_create_user(db, user_id)

    # Only full_completion certificate is supported
    # Phase badges are used for phase-level achievements instead
    if certificate_type != "full_completion":
        raise HTTPException(
            status_code=400,
            detail=(
                "Only 'full_completion' certificate type is supported. "
                "Phase achievements are tracked via badges."
            ),
        )

    (
        is_eligible,
        topics_completed,
        total_topics,
        percentage,
        existing_cert,
    ) = await _check_eligibility(db, user_id, certificate_type)

    if existing_cert:
        message = "Certificate already issued"
    elif is_eligible:
        cert_info = get_certificate_info(certificate_type)
        message = (
            f"Congratulations! You are eligible for the {cert_info['name']} certificate"
        )
    else:
        requirements = get_completion_requirements(certificate_type)
        min_pct = requirements["min_completion_percentage"]
        message = (
            f"Complete at least {min_pct}% of required topics to earn this certificate"
        )

    return CertificateEligibilityResponse(
        is_eligible=is_eligible,
        certificate_type=certificate_type,
        topics_completed=topics_completed,
        total_topics=total_topics,
        completion_percentage=round(percentage, 1),
        already_issued=existing_cert is not None,
        existing_certificate_id=existing_cert.id if existing_cert else None,
        message=message,
    )


@router.post("", response_model=CertificateResponse)
async def generate_certificate(
    request: CertificateRequest,
    user_id: UserId,
    db: DbSession,
) -> CertificateResponse:
    """Generate a completion certificate for eligible users."""
    await get_or_create_user(db, user_id)

    (
        is_eligible,
        topics_completed,
        total_topics,
        percentage,
        existing_cert,
    ) = await _check_eligibility(db, user_id, request.certificate_type)

    if existing_cert:
        raise HTTPException(
            status_code=409,
            detail="Certificate already issued. Use GET /certificates to retrieve it.",
        )

    if not is_eligible:
        raise HTTPException(
            status_code=403,
            detail=f"Not eligible for certificate. Current progress: {percentage:.1f}%",
        )

    # Generate unique verification code
    verification_code = generate_verification_code(user_id, request.certificate_type)

    # Create certificate record
    certificate = Certificate(
        user_id=user_id,
        certificate_type=request.certificate_type,
        verification_code=verification_code,
        recipient_name=request.recipient_name,
        issued_at=datetime.now(UTC),
        topics_completed=topics_completed,
        total_topics=total_topics,
    )
    db.add(certificate)

    # Log activity for earning certificate
    activity = UserActivity(
        user_id=user_id,
        activity_type=ActivityType.CERTIFICATE_EARNED,
        reference_id=request.certificate_type,
    )
    db.add(activity)

    await db.commit()
    await db.refresh(certificate)

    return CertificateResponse.model_validate(certificate)


@router.get("", response_model=UserCertificatesResponse)
async def get_user_certificates(
    user_id: UserId,
    db: DbSession,
) -> UserCertificatesResponse:
    """Get all certificates for the authenticated user."""
    await get_or_create_user(db, user_id)

    result = await db.execute(
        select(Certificate)
        .where(Certificate.user_id == user_id)
        .order_by(Certificate.issued_at.desc())
    )
    certificates = result.scalars().all()

    # Check full completion eligibility
    is_eligible, _, _, _, existing = await _check_eligibility(
        db, user_id, "full_completion"
    )

    return UserCertificatesResponse(
        certificates=[CertificateResponse.model_validate(c) for c in certificates],
        full_completion_eligible=is_eligible and existing is None,
    )


@router.get("/{certificate_id}", response_model=CertificateResponse)
async def get_certificate(
    certificate_id: int,
    user_id: UserId,
    db: DbSession,
) -> CertificateResponse:
    """Get a specific certificate by ID (must belong to authenticated user)."""
    result = await db.execute(
        select(Certificate).where(
            Certificate.id == certificate_id,
            Certificate.user_id == user_id,
        )
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    return CertificateResponse.model_validate(certificate)


@router.get("/{certificate_id}/svg")
async def get_certificate_svg(
    certificate_id: int,
    user_id: UserId,
    db: DbSession,
) -> Response:
    """Get the SVG image for a certificate."""
    result = await db.execute(
        select(Certificate).where(
            Certificate.id == certificate_id,
            Certificate.user_id == user_id,
        )
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    svg_content = generate_certificate_svg(
        recipient_name=certificate.recipient_name,
        certificate_type=certificate.certificate_type,
        verification_code=certificate.verification_code,
        issued_at=certificate.issued_at,
        topics_completed=certificate.topics_completed,
        total_topics=certificate.total_topics,
    )

    settings = get_settings()
    cache_control = (
        "no-store" if settings.environment.lower() == "development" else "public, max-age=3600"
    )

    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": (
                f'inline; filename="ltc-certificate-'
                f'{certificate.verification_code}.svg"'
            ),
            "Cache-Control": cache_control,
        },
    )


@router.get("/{certificate_id}/pdf")
async def get_certificate_pdf(
    certificate_id: int,
    user_id: UserId,
    db: DbSession,
) -> Response:
    """Get the PDF for a certificate."""
    result = await db.execute(
        select(Certificate).where(
            Certificate.id == certificate_id,
            Certificate.user_id == user_id,
        )
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    svg_content = generate_certificate_svg(
        recipient_name=certificate.recipient_name,
        certificate_type=certificate.certificate_type,
        verification_code=certificate.verification_code,
        issued_at=certificate.issued_at,
        topics_completed=certificate.topics_completed,
        total_topics=certificate.total_topics,
    )

    pdf_content = svg_to_pdf(svg_content)

    settings = get_settings()
    cache_control = (
        "no-store"
        if settings.environment.lower() == "development"
        else "public, max-age=3600"
    )

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ltc-certificate-'
                f'{certificate.verification_code}.pdf"'
            ),
            "Cache-Control": cache_control,
        },
    )


@router.get("/verify/{verification_code}", response_model=CertificateVerifyResponse)
async def verify_certificate(
    db: DbSession,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
) -> CertificateVerifyResponse:
    """Verify a certificate by its verification code (public endpoint)."""
    result = await db.execute(
        select(Certificate).where(Certificate.verification_code == verification_code)
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        return CertificateVerifyResponse(
            is_valid=False,
            certificate=None,
            message="Certificate not found. Please check the verification code.",
        )

    cert_info = get_certificate_info(certificate.certificate_type)
    issued_date = certificate.issued_at.strftime("%B %d, %Y")

    return CertificateVerifyResponse(
        is_valid=True,
        certificate=CertificateResponse.model_validate(certificate),
        message=f"Valid certificate for {cert_info['name']} issued on {issued_date}",
    )


@router.get("/verify/{verification_code}/svg")
async def get_verified_certificate_svg(
    db: DbSession,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
) -> Response:
    """Get the SVG image for a verified certificate (public endpoint)."""
    result = await db.execute(
        select(Certificate).where(Certificate.verification_code == verification_code)
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    svg_content = generate_certificate_svg(
        recipient_name=certificate.recipient_name,
        certificate_type=certificate.certificate_type,
        verification_code=certificate.verification_code,
        issued_at=certificate.issued_at,
        topics_completed=certificate.topics_completed,
        total_topics=certificate.total_topics,
    )

    settings = get_settings()
    cache_control = (
        "no-store" if settings.environment.lower() == "development" else "public, max-age=3600"
    )

    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": (
                f'inline; filename="ltc-certificate-'
                f'{certificate.verification_code}.svg"'
            ),
            "Cache-Control": cache_control,
        },
    )


@router.get("/verify/{verification_code}/pdf")
async def get_verified_certificate_pdf(
    db: DbSession,
    verification_code: str = Path(min_length=10, max_length=64),
    user_id: OptionalUserId = None,
) -> Response:
    """Get the PDF for a verified certificate (public endpoint)."""
    result = await db.execute(
        select(Certificate).where(Certificate.verification_code == verification_code)
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    svg_content = generate_certificate_svg(
        recipient_name=certificate.recipient_name,
        certificate_type=certificate.certificate_type,
        verification_code=certificate.verification_code,
        issued_at=certificate.issued_at,
        topics_completed=certificate.topics_completed,
        total_topics=certificate.total_topics,
    )

    pdf_content = svg_to_pdf(svg_content)

    settings = get_settings()
    cache_control = (
        "no-store"
        if settings.environment.lower() == "development"
        else "public, max-age=3600"
    )

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ltc-certificate-'
                f'{certificate.verification_code}.pdf"'
            ),
            "Cache-Control": cache_control,
        },
    )
