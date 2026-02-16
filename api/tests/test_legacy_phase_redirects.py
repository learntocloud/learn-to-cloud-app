"""Unit tests for legacy /phaseN* URL redirect middleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import URL
from starlette.responses import PlainTextResponse, RedirectResponse

from main import legacy_phase_url_redirects


@pytest.mark.unit
class TestLegacyPhaseRedirects:
    async def test_redirects_phase_root_no_trailing_slash(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase1")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/1"
        call_next.assert_not_awaited()

    async def test_redirects_phase_root_with_trailing_slash(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase0/")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/0"
        call_next.assert_not_awaited()

    async def test_redirects_phase_root_with_query_string(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase2?utm=abc")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/2?utm=abc"
        call_next.assert_not_awaited()

    async def test_redirects_phase_hyphen_variant(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase-6")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/6"
        call_next.assert_not_awaited()

    async def test_redirects_legacy_topic_slug(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase1/clibasics/")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/1/cli-basics"
        call_next.assert_not_awaited()

    async def test_redirects_known_topic_override(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase1/ctf")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/1/ctf-lab"
        call_next.assert_not_awaited()

    async def test_unknown_topic_falls_back_to_phase_root(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase3/does-not-exist")

        call_next = AsyncMock(return_value=PlainTextResponse("ok"))
        resp = await legacy_phase_url_redirects(request, call_next)

        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 308
        assert resp.headers["location"] == "/phase/3"
        call_next.assert_not_awaited()

    async def test_canonical_paths_pass_through(self) -> None:
        request = MagicMock()
        request.url = URL("https://testserver/phase/1")

        downstream = PlainTextResponse("ok")
        call_next = AsyncMock(return_value=downstream)
        resp = await legacy_phase_url_redirects(request, call_next)

        assert resp is downstream
        call_next.assert_awaited_once()
