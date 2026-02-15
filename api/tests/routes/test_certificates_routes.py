"""Unit tests for certificate routes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routes.certificates_routes import (
    get_certificate_pdf_endpoint,
    get_certificate_png_endpoint,
    get_verified_certificate_pdf_endpoint,
    get_verified_certificate_png_endpoint,
)
from schemas import CertificateData


def _fake_certificate() -> CertificateData:
    """Build a minimal CertificateData for testing."""
    return CertificateData(
        id=1,
        verification_code="ABC1234567",
        recipient_name="Test User",
        issued_at=datetime(2024, 6, 1),
        phases_completed=7,
        total_phases=7,
    )


@pytest.mark.unit
class TestVerifiedCertificatePdf:
    """Tests for GET /api/certificates/verify/{code}/pdf."""

    async def test_returns_pdf_response(self):
        """Returns PDF content when certificate is found."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.verify_certificate",
                autospec=True,
                return_value=cert,
            ) as mock_verify,
            patch(
                "routes.certificates_routes.generate_certificate_pdf",
                autospec=True,
                return_value=b"%PDF-fake",
            ),
        ):
            result = await get_verified_certificate_pdf_endpoint(
                mock_request, db=mock_db, verification_code="ABC1234567"
            )

        mock_verify.assert_awaited_once_with(mock_db, "ABC1234567")
        assert result.media_type == "application/pdf"
        assert result.body == b"%PDF-fake"

    async def test_returns_404_when_not_found(self):
        """Returns 404 when certificate doesn't exist."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.certificates_routes.verify_certificate",
            autospec=True,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_verified_certificate_pdf_endpoint(
                    mock_request, db=mock_db, verification_code="NOTFOUND1234"
                )

        assert exc_info.value.status_code == 404

    async def test_returns_501_on_runtime_error(self):
        """RuntimeError from PDF generation becomes 501."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.verify_certificate",
                autospec=True,
                return_value=cert,
            ),
            patch(
                "routes.certificates_routes.generate_certificate_pdf",
                autospec=True,
                side_effect=RuntimeError("playwright not installed"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_verified_certificate_pdf_endpoint(
                    mock_request, db=mock_db, verification_code="ABC1234567"
                )

        assert exc_info.value.status_code == 501


@pytest.mark.unit
class TestVerifiedCertificatePng:
    """Tests for GET /api/certificates/verify/{code}/png."""

    async def test_returns_png_response(self):
        """Returns PNG content when certificate is found."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.verify_certificate",
                autospec=True,
                return_value=cert,
            ) as mock_verify,
            patch(
                "routes.certificates_routes.generate_certificate_png",
                autospec=True,
                return_value=b"\x89PNG-fake",
            ),
        ):
            result = await get_verified_certificate_png_endpoint(
                mock_request, db=mock_db, verification_code="ABC1234567", scale=2.0
            )

        mock_verify.assert_awaited_once_with(mock_db, "ABC1234567")
        assert result.media_type == "image/png"
        assert result.body == b"\x89PNG-fake"

    async def test_returns_404_when_not_found(self):
        """Returns 404 when certificate doesn't exist."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.certificates_routes.verify_certificate",
            autospec=True,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_verified_certificate_png_endpoint(
                    mock_request,
                    db=mock_db,
                    verification_code="NOTFOUND1234",
                    scale=2.0,
                )

        assert exc_info.value.status_code == 404

    async def test_returns_501_on_runtime_error(self):
        """RuntimeError from PNG generation becomes 501."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.verify_certificate",
                autospec=True,
                return_value=cert,
            ),
            patch(
                "routes.certificates_routes.generate_certificate_png",
                autospec=True,
                side_effect=RuntimeError("playwright not installed"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_verified_certificate_png_endpoint(
                    mock_request, db=mock_db, verification_code="ABC1234567", scale=2.0
                )

        assert exc_info.value.status_code == 501


@pytest.mark.unit
class TestUserCertificatePdf:
    """Tests for GET /api/certificates/mine/pdf."""

    async def test_returns_pdf_response(self):
        """Returns PDF for authenticated user's certificate."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.get_user_certificate",
                autospec=True,
                return_value=cert,
            ) as mock_get,
            patch(
                "routes.certificates_routes.generate_certificate_pdf",
                autospec=True,
                return_value=b"%PDF-user",
            ),
        ):
            result = await get_certificate_pdf_endpoint(
                mock_request, user_id=1, db=mock_db
            )

        mock_get.assert_awaited_once_with(mock_db, 1)
        assert result.media_type == "application/pdf"
        assert result.body == b"%PDF-user"

    async def test_returns_404_when_not_found(self):
        """Returns 404 when user has no certificate."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.certificates_routes.get_user_certificate",
            autospec=True,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_certificate_pdf_endpoint(mock_request, user_id=1, db=mock_db)

        assert exc_info.value.status_code == 404

    async def test_returns_501_on_runtime_error(self):
        """RuntimeError from PDF generation becomes 501."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.get_user_certificate",
                autospec=True,
                return_value=cert,
            ),
            patch(
                "routes.certificates_routes.generate_certificate_pdf",
                autospec=True,
                side_effect=RuntimeError("not available"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_certificate_pdf_endpoint(mock_request, user_id=1, db=mock_db)

        assert exc_info.value.status_code == 501


@pytest.mark.unit
class TestUserCertificatePng:
    """Tests for GET /api/certificates/mine/png."""

    async def test_returns_png_response(self):
        """Returns PNG for authenticated user's certificate."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.get_user_certificate",
                autospec=True,
                return_value=cert,
            ) as mock_get,
            patch(
                "routes.certificates_routes.generate_certificate_png",
                autospec=True,
                return_value=b"\x89PNG-user",
            ),
        ):
            result = await get_certificate_png_endpoint(
                mock_request, user_id=1, db=mock_db, scale=2.0
            )

        mock_get.assert_awaited_once_with(mock_db, 1)
        assert result.media_type == "image/png"
        assert result.body == b"\x89PNG-user"

    async def test_returns_404_when_not_found(self):
        """Returns 404 when user has no certificate."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.certificates_routes.get_user_certificate",
            autospec=True,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_certificate_png_endpoint(
                    mock_request, user_id=1, db=mock_db, scale=2.0
                )

        assert exc_info.value.status_code == 404

    async def test_returns_501_on_runtime_error(self):
        """RuntimeError from PNG generation becomes 501."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        cert = _fake_certificate()

        with (
            patch(
                "routes.certificates_routes.get_user_certificate",
                autospec=True,
                return_value=cert,
            ),
            patch(
                "routes.certificates_routes.generate_certificate_png",
                autospec=True,
                side_effect=RuntimeError("not available"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_certificate_png_endpoint(
                    mock_request, user_id=1, db=mock_db, scale=2.0
                )

        assert exc_info.value.status_code == 501
