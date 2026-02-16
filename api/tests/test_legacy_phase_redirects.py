"""Unit tests for legacy /phaseN* URL redirect middleware."""

from unittest.mock import patch

import pytest

# Deterministic alias mapping for tests — no dependency on YAML content files.
_TEST_ALIASES: dict[str, dict[str, str]] = {
    "1": {
        "clibasics": "cli-basics",
        "ctf": "ctf-lab",
        "versioncontrol": "developer-setup",
    },
    "2": {
        "networkingfundamentals": "fundamentals",
        "portsandprotocols": "protocols",
        "troubleshooting": "troubleshooting-lab",
    },
}

_PATCH_TARGET = "services.redirect_service._topic_slug_aliases_by_phase"


@pytest.mark.unit
class TestResolveLegacyPhaseRedirect:
    """Tests for the pure redirect-resolution function."""

    @pytest.fixture(autouse=True)
    def _mock_aliases(self):
        with patch(_PATCH_TARGET, return_value=_TEST_ALIASES):
            yield

    def test_phase_root_no_trailing_slash(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase1") == "/phase/1"

    def test_phase_root_with_trailing_slash(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase0/") == "/phase/0"

    def test_phase_hyphen_variant(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase-6") == "/phase/6"

    def test_phase_underscore_variant(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase_4") == "/phase/4"

    def test_multi_digit_phase(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase10") == "/phase/10"

    def test_legacy_topic_slug(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert (
            resolve_legacy_phase_redirect("/phase1/clibasics/") == "/phase/1/cli-basics"
        )

    def test_legacy_topic_slug_preserves_remainder(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert (
            resolve_legacy_phase_redirect("/phase1/clibasics/step1/substep2")
            == "/phase/1/cli-basics/step1/substep2"
        )

    def test_known_topic_override(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase1/ctf") == "/phase/1/ctf-lab"

    def test_unknown_topic_falls_back_to_phase_root(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase3/does-not-exist") == "/phase/3"

    def test_canonical_path_returns_none(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase/1") is None

    def test_canonical_path_with_topic_returns_none(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phase/1/cli-basics") is None

    def test_unrelated_path_returns_none(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/dashboard") is None

    def test_no_digits_returns_none(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        assert resolve_legacy_phase_redirect("/phases") is None

    def test_double_slashes_normalised(self) -> None:
        from services.redirect_service import resolve_legacy_phase_redirect

        result = resolve_legacy_phase_redirect("/phase1/clibasics//step1")
        assert result == "/phase/1/cli-basics/step1"


@pytest.mark.unit
class TestLegacyPhaseRedirectMiddleware:
    """Integration test: middleware returns 308 or passes through."""

    @pytest.fixture(autouse=True)
    def _mock_aliases(self):
        with patch(_PATCH_TARGET, return_value=_TEST_ALIASES):
            yield

    async def test_redirects_with_query_string(self) -> None:
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        from core.redirects import LegacyPhaseRedirectMiddleware
        from services.redirect_service import resolve_legacy_phase_redirect

        async def homepage(request):
            return PlainTextResponse("ok")

        inner_app = Starlette(routes=[Route("/phase/{phase_id:int}", homepage)])
        inner_app.add_middleware(
            LegacyPhaseRedirectMiddleware, resolver=resolve_legacy_phase_redirect
        )
        client = TestClient(inner_app, raise_server_exceptions=False)

        resp = client.get("/phase2?utm=abc", follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/2?utm=abc"

    async def test_canonical_paths_pass_through(self) -> None:
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        from core.redirects import LegacyPhaseRedirectMiddleware
        from services.redirect_service import resolve_legacy_phase_redirect

        async def homepage(request):
            return PlainTextResponse("ok")

        inner_app = Starlette(routes=[Route("/phase/{phase_id:int}", homepage)])
        inner_app.add_middleware(
            LegacyPhaseRedirectMiddleware, resolver=resolve_legacy_phase_redirect
        )
        client = TestClient(inner_app, raise_server_exceptions=False)

        resp = client.get("/phase/1")
        assert resp.status_code == 200
        assert resp.text == "ok"
