from datetime import UTC, datetime

from rendering.certificates import generate_certificate_svg


def test_certificate_svg_inlines_brand_logo() -> None:
    """Test that the certificate SVG rendering correctly inlines the brand logo.

    This test uses the rendering module directly since it's testing the
    low-level SVG generation, not the service-layer business logic.
    """
    svg = generate_certificate_svg(
        recipient_name="Gwyneth",
        certificate_type="full_completion",
        verification_code="LTC-TEST-LOGO",
        issued_at=datetime(2026, 1, 13, tzinfo=UTC),
        phases_completed=7,
        total_phases=7,
    )

    assert "Brand logo (Logo-03.svg)" in svg
    assert '<svg x="280" y="40"' in svg

    assert "<image" not in svg

    assert "ltcLogo-" in svg

    assert "ltcLogoTextGradient" in svg
    assert ".st0{fill:url(#ltcLogoTextGradient);}" in svg
    assert ".st0{fill:#124D99;}" not in svg
