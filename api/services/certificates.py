"""Certificate business logic for Learn to Cloud.

This module handles certificate business logic:
- Certificate eligibility checking (based on progress)
- Certificate creation with activity logging
- Certificate verification
- Verification code generation
- SVG and PDF generation (delegating to rendering module)

Routes should delegate all certificate business logic to this module.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType, Certificate
from rendering.certificates import (
    generate_certificate_svg as _render_certificate_svg,
)
from rendering.certificates import (
    get_certificate_display_info as get_certificate_info,
)
from rendering.certificates import (
    svg_to_pdf as _svg_to_pdf,
)
from repositories.activity import ActivityRepository
from repositories.certificate import CertificateRepository
from services.progress import fetch_user_progress


@dataclass(frozen=True)
class CertificateData:
    """DTO for a certificate (service-layer return type)."""

    id: int
    certificate_type: str
    verification_code: str
    recipient_name: str
    issued_at: datetime
    phases_completed: int
    total_phases: int


def _to_certificate_data(certificate: Certificate) -> CertificateData:
    return CertificateData(
        id=certificate.id,
        certificate_type=certificate.certificate_type,
        verification_code=certificate.verification_code,
        recipient_name=certificate.recipient_name,
        issued_at=certificate.issued_at,
        phases_completed=certificate.phases_completed,
        total_phases=certificate.total_phases,
    )


def generate_verification_code(user_id: str, certificate_type: str) -> str:
    """Generate a unique, verifiable certificate code.

    Format: LTC-{hash}-{random}
    The hash includes user_id, certificate_type, and timestamp for uniqueness.
    """
    timestamp = datetime.now(UTC).isoformat()
    data = f"{user_id}:{certificate_type}:{timestamp}"
    hash_part = hashlib.sha256(data.encode()).hexdigest()[:12].upper()
    random_part = secrets.token_hex(4).upper()
    return f"LTC-{hash_part}-{random_part}"


@dataclass
class EligibilityResult:
    """Result of certificate eligibility check."""

    is_eligible: bool
    phases_completed: int
    total_phases: int
    completion_percentage: float
    existing_certificate: CertificateData | None
    message: str


async def check_eligibility(
    db: AsyncSession,
    user_id: str,
    certificate_type: str,
) -> EligibilityResult:
    """Check if user is eligible for a certificate.

    Uses the centralized progress system to determine eligibility.
    A user is eligible for full_completion certificate when ALL phases are complete.
    """
    if certificate_type != "full_completion":
        raise ValueError(
            f"Unknown certificate type: {certificate_type}. "
            "Only 'full_completion' is supported."
        )

    cert_repo = CertificateRepository(db)
    existing_cert = await cert_repo.get_by_user_and_type(user_id, certificate_type)

    progress = await fetch_user_progress(db, user_id)

    phases_completed = progress.phases_completed
    total_phases = progress.total_phases
    percentage = (phases_completed / total_phases) * 100 if total_phases > 0 else 0.0

    existing_cert_data = _to_certificate_data(existing_cert) if existing_cert else None

    if existing_cert_data:
        message = "Certificate already issued"
    elif progress.is_program_complete:
        cert_info = get_certificate_info(certificate_type)
        message = (
            f"Congratulations! You are eligible for the {cert_info['name']} certificate"
        )
    else:
        message = "Complete all phases to earn this certificate"

    return EligibilityResult(
        is_eligible=progress.is_program_complete,
        phases_completed=phases_completed,
        total_phases=total_phases,
        completion_percentage=percentage,
        existing_certificate=existing_cert_data,
        message=message,
    )


@dataclass
class CreateCertificateResult:
    """Result of certificate creation."""

    certificate: CertificateData
    verification_code: str


class CertificateAlreadyExistsError(Exception):
    """Raised when certificate already exists for user."""

    pass


class NotEligibleError(Exception):
    """Raised when user is not eligible for certificate."""

    def __init__(
        self, phases_completed: int, total_phases: int, message: str | None = None
    ):
        self.phases_completed = phases_completed
        self.total_phases = total_phases
        super().__init__(
            message
            or f"Not eligible: {phases_completed}/{total_phases} phases completed"
        )


async def create_certificate(
    db: AsyncSession,
    user_id: str,
    certificate_type: str,
    recipient_name: str,
) -> CreateCertificateResult:
    """Create a new certificate for an eligible user.

    This handles all certificate creation business logic:
    - Eligibility checking
    - Verification code generation
    - Certificate record creation
    - Activity logging

    Args:
        db: Database session
        user_id: The user's ID
        certificate_type: Type of certificate (e.g., "full_completion")
        recipient_name: Name to display on certificate

    Returns:
        CreateCertificateResult with certificate and verification code

    Raises:
        CertificateAlreadyExistsError: If certificate already issued
        NotEligibleError: If user doesn't meet requirements
    """
    eligibility = await check_eligibility(db, user_id, certificate_type)

    if eligibility.existing_certificate:
        raise CertificateAlreadyExistsError(
            "Certificate already issued. Use GET /certificates to retrieve it."
        )

    if not eligibility.is_eligible:
        raise NotEligibleError(
            phases_completed=eligibility.phases_completed,
            total_phases=eligibility.total_phases,
            message=(
                f"Not eligible for certificate. "
                f"Complete all {eligibility.total_phases} phases first. "
                f"Current: {eligibility.phases_completed}/{eligibility.total_phases}"
            ),
        )

    verification_code = generate_verification_code(user_id, certificate_type)

    cert_repo = CertificateRepository(db)
    certificate = await cert_repo.create(
        user_id=user_id,
        certificate_type=certificate_type,
        verification_code=verification_code,
        recipient_name=recipient_name,
        phases_completed=eligibility.phases_completed,
        total_phases=eligibility.total_phases,
    )

    today = datetime.now(UTC).date()
    activity_repo = ActivityRepository(db)
    await activity_repo.log_activity(
        user_id=user_id,
        activity_type=ActivityType.CERTIFICATE_EARNED,
        activity_date=today,
        reference_id=certificate_type,
    )

    return CreateCertificateResult(
        certificate=_to_certificate_data(certificate),
        verification_code=verification_code,
    )


async def get_user_certificates_with_eligibility(
    db: AsyncSession,
    user_id: str,
) -> tuple[list[CertificateData], bool]:
    """Get all certificates for a user plus eligibility status.

    Args:
        db: Database session
        user_id: The user's ID

    Returns:
        Tuple of (certificates list, full_completion_eligible flag)
    """
    cert_repo = CertificateRepository(db)
    certificates = await cert_repo.get_by_user(user_id)

    eligibility = await check_eligibility(db, user_id, "full_completion")
    full_completion_eligible = (
        eligibility.is_eligible and eligibility.existing_certificate is None
    )

    return [_to_certificate_data(c) for c in certificates], full_completion_eligible


async def get_certificate_by_id(
    db: AsyncSession,
    certificate_id: int,
    user_id: str,
) -> CertificateData | None:
    """Get a specific certificate by ID (must belong to user).

    Args:
        db: Database session
        certificate_id: The certificate ID
        user_id: The user's ID

    Returns:
        Certificate if found and owned by user, else None
    """
    cert_repo = CertificateRepository(db)
    cert = await cert_repo.get_by_id_and_user(certificate_id, user_id)
    return _to_certificate_data(cert) if cert else None


async def verify_certificate(
    db: AsyncSession,
    verification_code: str,
) -> CertificateData | None:
    """Verify a certificate by its verification code.

    Args:
        db: Database session
        verification_code: The verification code to look up

    Returns:
        Certificate if valid, else None
    """
    cert_repo = CertificateRepository(db)
    cert = await cert_repo.get_by_verification_code(verification_code)
    return _to_certificate_data(cert) if cert else None


@dataclass
class VerificationResult:
    """Result of certificate verification."""

    is_valid: bool
    certificate: CertificateData | None
    message: str


async def verify_certificate_with_message(
    db: AsyncSession,
    verification_code: str,
) -> VerificationResult:
    """Verify a certificate and return a user-friendly result.

    Args:
        db: Database session
        verification_code: The verification code to look up

    Returns:
        VerificationResult with validation status and message
    """
    certificate = await verify_certificate(db, verification_code)

    if not certificate:
        return VerificationResult(
            is_valid=False,
            certificate=None,
            message="Certificate not found. Please check the verification code.",
        )

    cert_info = get_certificate_info(certificate.certificate_type)
    issued_date = certificate.issued_at.strftime("%B %d, %Y")

    return VerificationResult(
        is_valid=True,
        certificate=certificate,
        message=f"Valid certificate for {cert_info['name']} issued on {issued_date}",
    )


def generate_certificate_svg(certificate: CertificateData) -> str:
    """Generate SVG content for a certificate.

    This is a service-layer function that delegates to the rendering module.
    Routes should call this instead of the rendering module directly.

    Args:
        certificate: The certificate to render

    Returns:
        SVG content as a string
    """
    return _render_certificate_svg(
        recipient_name=certificate.recipient_name,
        certificate_type=certificate.certificate_type,
        verification_code=certificate.verification_code,
        issued_at=certificate.issued_at,
        phases_completed=certificate.phases_completed,
        total_phases=certificate.total_phases,
    )


def generate_certificate_pdf(certificate: CertificateData) -> bytes:
    """Generate PDF content for a certificate.

    This is a service-layer function that delegates to the rendering module.
    Routes should call this instead of the rendering module directly.

    Args:
        certificate: The certificate to render

    Returns:
        PDF content as bytes
    """
    svg_content = generate_certificate_svg(certificate)
    return _svg_to_pdf(svg_content)
