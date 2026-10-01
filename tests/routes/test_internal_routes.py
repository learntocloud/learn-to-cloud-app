"""Unit tests for internal operational routes."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from learn_to_cloud.routes.internal_routes import smoke_verification


def _request_with_auth(*, allowed_client_id: str = "") -> MagicMock:
    request = MagicMock()
    request.app.state.settings.smoke_test.allowed_client_id = allowed_client_id
    request.app.state.session_maker = MagicMock()
    return request


def _principal(*, app_id: str, roles: list[str]) -> str:
    claims = [{"typ": "azp", "val": app_id}]
    claims.extend({"typ": "roles", "val": role} for role in roles)
    payload = {
        "auth_typ": "aad",
        "claims": claims,
        "name_typ": "name",
        "role_typ": "roles",
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.unit
class TestSmokeVerificationEndpoint:
    """Tests for POST /internal/smoke/verification."""

    async def test_returns_401_when_authentication_missing(self):
        request = _request_with_auth()

        with pytest.raises(HTTPException) as exc_info:
            await smoke_verification(
                request,
                x_ms_client_principal=None,
                x_ms_client_principal_id=None,
            )

        assert exc_info.value.status_code == 401

    async def test_returns_200_for_authorized_entra_principal(self):
        client_id = "80656257-8f52-4889-95c4-d594c29c82ae"
        request = _request_with_auth(allowed_client_id=client_id)

        with patch(
            "learn_to_cloud.routes.internal_routes.run_submit_smoke_check",
            new_callable=AsyncMock,
            return_value={"requirement_slug": "phase0-req"},
        ):
            result = await smoke_verification(
                request,
                x_ms_client_principal=_principal(
                    app_id=client_id, roles=["Smoke.Trigger"]
                ),
                x_ms_client_principal_id="deployment-service-principal",
            )

        assert result == {"status": "ok", "requirement_slug": "phase0-req"}

    @pytest.mark.parametrize(
        ("principal", "expected_status"),
        [
            ("not-base64", 401),
            (_principal(app_id="other-client", roles=["Smoke.Trigger"]), 403),
            (
                _principal(
                    app_id="80656257-8f52-4889-95c4-d594c29c82ae",
                    roles=[],
                ),
                403,
            ),
        ],
    )
    async def test_rejects_invalid_entra_principal(
        self, principal: str, expected_status: int
    ):
        request = _request_with_auth(
            allowed_client_id="80656257-8f52-4889-95c4-d594c29c82ae"
        )

        with pytest.raises(HTTPException) as exc_info:
            await smoke_verification(
                request,
                x_ms_client_principal=principal,
                x_ms_client_principal_id="deployment-service-principal",
            )

        assert exc_info.value.status_code == expected_status

    async def test_returns_503_when_check_raises(self):
        client_id = "80656257-8f52-4889-95c4-d594c29c82ae"
        request = _request_with_auth(allowed_client_id=client_id)

        with patch(
            "learn_to_cloud.routes.internal_routes.run_submit_smoke_check",
            new_callable=AsyncMock,
            side_effect=RuntimeError("schema mismatch"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await smoke_verification(
                    request,
                    x_ms_client_principal=_principal(
                        app_id=client_id, roles=["Smoke.Trigger"]
                    ),
                    x_ms_client_principal_id="deployment-service-principal",
                )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Verification smoke check failed."
