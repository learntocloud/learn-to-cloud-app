"""Tests for certificate rendering module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from rendering.certificates import (
    CERTIFICATE_SUBTITLE,
    CERTIFICATE_TITLE,
    ISSUER_NAME,
    ISSUER_URL,
    PHASE_DISPLAY_INFO,
    _get_logo_inline_svg,
    generate_certificate_svg,
    get_certificate_display_info,
    svg_to_base64_data_uri,
    svg_to_pdf,
    svg_to_png,
)

pytestmark = pytest.mark.unit


class TestConstants:
    """Tests for module constants."""

    def test_certificate_title_is_set(self):
        """Test certificate title constant."""
        assert CERTIFICATE_TITLE == "Learn to Cloud"

    def test_certificate_subtitle_is_set(self):
        """Test certificate subtitle constant."""
        assert CERTIFICATE_SUBTITLE == "Certificate of Completion"

    def test_issuer_name_is_set(self):
        """Test issuer name constant."""
        assert ISSUER_NAME == "Learn to Cloud"

    def test_issuer_url_is_set(self):
        """Test issuer URL constant."""
        assert ISSUER_URL == "https://learntocloud.guide"

    def test_phase_display_info_has_all_phases(self):
        """Test all phases have display info."""
        expected_phases = [
            "phase_0",
            "phase_1",
            "phase_2",
            "phase_3",
            "phase_4",
            "phase_5",
            "full_completion",
        ]
        for phase in expected_phases:
            assert phase in PHASE_DISPLAY_INFO
            assert "name" in PHASE_DISPLAY_INFO[phase]
            assert "description" in PHASE_DISPLAY_INFO[phase]


class TestGetCertificateDisplayInfo:
    """Tests for get_certificate_display_info function."""

    def test_returns_info_for_known_phase(self):
        """Test returns correct info for known phase."""
        info = get_certificate_display_info("phase_1")

        assert info["name"] == "Linux & Bash"
        assert "Command Line" in info["description"]

    def test_returns_full_completion_for_unknown_phase(self):
        """Test returns full_completion info for unknown phase."""
        info = get_certificate_display_info("unknown_phase")

        assert info == PHASE_DISPLAY_INFO["full_completion"]

    def test_returns_full_completion_info(self):
        """Test returns correct info for full_completion."""
        info = get_certificate_display_info("full_completion")

        assert info["name"] == "Full Program Completion"
        assert "All Phases" in info["description"]


class TestGetLogoInlineSvg:
    """Tests for _get_logo_inline_svg function."""

    def test_returns_none_when_file_not_found(self):
        """Test returns None when logo file doesn't exist."""
        with patch("rendering.certificates._LOGO_SVG_PATH") as mock_path:
            mock_path.read_text.side_effect = OSError("File not found")

            # Clear cache
            _get_logo_inline_svg.cache_clear()

            result = _get_logo_inline_svg()

            assert result is None

    def test_returns_none_for_empty_file(self):
        """Test returns None for empty SVG file."""
        with patch("rendering.certificates._LOGO_SVG_PATH") as mock_path:
            mock_path.read_text.return_value = ""

            _get_logo_inline_svg.cache_clear()

            result = _get_logo_inline_svg()

            assert result is None

    def test_returns_none_for_invalid_svg(self):
        """Test returns None for invalid SVG content."""
        with patch("rendering.certificates._LOGO_SVG_PATH") as mock_path:
            mock_path.read_text.return_value = "not an svg"

            _get_logo_inline_svg.cache_clear()

            result = _get_logo_inline_svg()

            assert result is None

    def test_returns_svg_for_valid_file(self):
        """Test returns inline SVG for valid file."""
        valid_svg = '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'

        with patch("rendering.certificates._LOGO_SVG_PATH") as mock_path:
            mock_path.read_text.return_value = valid_svg

            _get_logo_inline_svg.cache_clear()

            result = _get_logo_inline_svg()

            assert result is not None
            assert "<svg" in result
            assert "circle" in result

    def test_prefixes_ids_to_avoid_collisions(self):
        """Test prefixes IDs in the logo SVG."""
        svg_with_id = (
            '<svg viewBox="0 0 100 100">'
            '<defs><linearGradient id="grad1"/></defs>'
            '<rect id="rect1"/>'
            "</svg>"
        )

        with patch("rendering.certificates._LOGO_SVG_PATH") as mock_path:
            mock_path.read_text.return_value = svg_with_id

            _get_logo_inline_svg.cache_clear()

            result = _get_logo_inline_svg()

            assert result is not None
            assert 'id="ltcLogo-grad1"' in result or "ltcLogo-" in result

    def test_removes_script_tags(self):
        """Test removes script tags for security."""
        svg_with_script = (
            '<svg viewBox="0 0 100 100"><script>alert("xss")</script><rect/></svg>'
        )

        with patch("rendering.certificates._LOGO_SVG_PATH") as mock_path:
            mock_path.read_text.return_value = svg_with_script

            _get_logo_inline_svg.cache_clear()

            result = _get_logo_inline_svg()

            assert result is not None
            assert "<script" not in result
            assert "alert" not in result


class TestGenerateCertificateSvg:
    """Tests for generate_certificate_svg function."""

    def test_generates_valid_svg(self):
        """Test generates valid SVG structure."""
        svg = generate_certificate_svg(
            recipient_name="John Doe",
            certificate_type="full_completion",
            verification_code="LTC-ABC-123",
            issued_at=datetime(2026, 1, 24, 12, 0, 0, tzinfo=UTC),
            phases_completed=7,
            total_phases=7,
        )

        assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_includes_recipient_name(self):
        """Test includes recipient name in SVG."""
        svg = generate_certificate_svg(
            recipient_name="Jane Smith",
            certificate_type="phase_1",
            verification_code="LTC-XYZ-789",
            issued_at=datetime.now(UTC),
            phases_completed=1,
            total_phases=7,
        )

        assert "Jane Smith" in svg

    def test_escapes_html_in_recipient_name(self):
        """Test escapes HTML special characters in name."""
        svg = generate_certificate_svg(
            recipient_name="<script>alert('xss')</script>",
            certificate_type="phase_1",
            verification_code="LTC-XYZ-789",
            issued_at=datetime.now(UTC),
            phases_completed=1,
            total_phases=7,
        )

        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_includes_verification_code(self):
        """Test includes verification code in SVG."""
        svg = generate_certificate_svg(
            recipient_name="Test User",
            certificate_type="full_completion",
            verification_code="LTC-VERIFY-CODE",
            issued_at=datetime.now(UTC),
            phases_completed=7,
            total_phases=7,
        )

        assert "LTC-VERIFY-CODE" in svg

    def test_includes_verification_url(self):
        """Test includes verification URL in SVG."""
        svg = generate_certificate_svg(
            recipient_name="Test User",
            certificate_type="full_completion",
            verification_code="LTC-ABC-123",
            issued_at=datetime.now(UTC),
            phases_completed=7,
            total_phases=7,
        )

        assert f"{ISSUER_URL}/verify/LTC-ABC-123" in svg

    def test_includes_issued_date(self):
        """Test includes formatted issued date."""
        svg = generate_certificate_svg(
            recipient_name="Test User",
            certificate_type="full_completion",
            verification_code="LTC-ABC-123",
            issued_at=datetime(2026, 1, 24, tzinfo=UTC),
            phases_completed=7,
            total_phases=7,
        )

        assert "January 24, 2026" in svg

    def test_includes_phase_count(self):
        """Test includes phases completed count."""
        svg = generate_certificate_svg(
            recipient_name="Test User",
            certificate_type="full_completion",
            verification_code="LTC-ABC-123",
            issued_at=datetime.now(UTC),
            phases_completed=5,
            total_phases=7,
        )

        assert "5/7" in svg

    def test_includes_certificate_type_name(self):
        """Test includes certificate type display name."""
        svg = generate_certificate_svg(
            recipient_name="Test User",
            certificate_type="phase_2",
            verification_code="LTC-ABC-123",
            issued_at=datetime.now(UTC),
            phases_completed=2,
            total_phases=7,
        )

        assert "Programming &amp; APIs" in svg or "Programming" in svg


class TestSvgToBase64DataUri:
    """Tests for svg_to_base64_data_uri function."""

    def test_returns_data_uri(self):
        """Test returns proper data URI format."""
        svg = "<svg><rect/></svg>"
        result = svg_to_base64_data_uri(svg)

        assert result.startswith("data:image/svg+xml;base64,")

    def test_encodes_svg_content(self):
        """Test properly base64 encodes SVG content."""
        import base64

        svg = "<svg><circle cx='50' cy='50' r='40'/></svg>"
        result = svg_to_base64_data_uri(svg)

        # Extract base64 part
        base64_part = result.split(",")[1]
        decoded = base64.b64decode(base64_part).decode("utf-8")

        assert decoded == svg


class TestSvgToPdf:
    """Tests for svg_to_pdf function."""

    def test_raises_runtime_error_without_cairo(self):
        """Test raises RuntimeError when cairo not installed."""
        with patch.dict("sys.modules", {"cairosvg": None}):
            with patch(
                "builtins.__import__",
                side_effect=OSError("cannot load library 'cairo'"),
            ):
                with pytest.raises(RuntimeError, match="Cairo library"):
                    svg_to_pdf("<svg></svg>")

    def test_converts_svg_to_pdf_bytes(self):
        """Test converts SVG to PDF bytes when cairo available."""
        mock_cairosvg = MagicMock()
        mock_cairosvg.svg2pdf.return_value = b"%PDF-1.4 mock pdf content"

        with patch.dict("sys.modules", {"cairosvg": mock_cairosvg}):
            # Re-import to use mocked module
            from rendering import certificates

            # Patch the import inside the function
            with patch(
                "builtins.__import__",
                return_value=mock_cairosvg,
            ):
                certificates.svg_to_pdf("<svg></svg>")

                # The function should have been called
                mock_cairosvg.svg2pdf.assert_called_once()


class TestSvgToPng:
    """Tests for svg_to_png function."""

    def test_raises_runtime_error_without_cairo(self):
        """Test raises RuntimeError when cairo not installed."""
        with patch.dict("sys.modules", {"cairosvg": None}):
            with patch(
                "builtins.__import__",
                side_effect=OSError("cannot load library 'cairo'"),
            ):
                with pytest.raises(RuntimeError, match="Cairo library"):
                    svg_to_png("<svg></svg>")

    def test_uses_scale_parameter(self):
        """Test passes scale parameter to cairosvg."""
        mock_cairosvg = MagicMock()
        mock_cairosvg.svg2png.return_value = b"\x89PNG mock png content"

        with patch.dict("sys.modules", {"cairosvg": mock_cairosvg}):
            from rendering import certificates

            with patch("builtins.__import__", return_value=mock_cairosvg):
                certificates.svg_to_png("<svg></svg>", scale=3.0)

                mock_cairosvg.svg2png.assert_called_once()
                call_kwargs = mock_cairosvg.svg2png.call_args[1]
                assert call_kwargs.get("scale") == 3.0
