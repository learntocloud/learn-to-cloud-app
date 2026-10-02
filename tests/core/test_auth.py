"""Tests for session identities, authentication policies, and OAuth registration."""

from importlib import import_module, util

import pytest

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    IdentityRejectionReason,
    init_oauth,
    oauth,
    validate_identity,
)
from learn_to_cloud.core.config import OAuthConfig


def test_authlib_uses_supported_http_client() -> None:
    """Require Authlib's supported transport when its compatibility shim exists."""
    module_name = "authlib.integrations.httpx_client._compat"
    if util.find_spec(module_name) is None:
        return

    compat = import_module(module_name)
    assert compat.httpx2.__name__ == "httpx2", (
        "Authlib is using its deprecated httpx fallback. Add httpx2 and update "
        "OAuth transport exception handling before upgrading Authlib."
    )


@pytest.mark.unit
class TestValidateIdentity:
    @pytest.mark.parametrize(
        "user_id",
        [
            True,
            42.0,
            "42",
            0,
            -1,
            2**63,
        ],
    )
    def test_rejects_invalid_ids_without_coercion(self, user_id):
        assert (
            validate_identity(user_id, "testuser")
            == IdentityRejectionReason.INVALID_USER_ID
        )

    @pytest.mark.parametrize(
        "username",
        [
            None,
            "",
            " ",
            "a" * 256,
            "private\x00name",
            "private\ud800name",
        ],
    )
    def test_rejects_unusable_usernames(self, username):
        assert (
            validate_identity(42, username)
            == IdentityRejectionReason.INVALID_GITHUB_USERNAME
        )

    @pytest.mark.parametrize(
        "username",
        ["a", "a" * 255, "MiXeD", " user ", "a.b"],
    )
    def test_preserves_names_without_signup_rules(self, username):
        assert validate_identity(42, username) == AuthenticatedUser(42, username)


@pytest.mark.unit
class TestInitOauth:
    """Test init_oauth registers GitHub provider."""

    def test_registers_github_when_client_id_set(self):
        # Clear any existing registration
        oauth._clients.pop("github", None)

        init_oauth(
            OAuthConfig(client_id="test-client-id", client_secret="test-client-secret")
        )

        assert "github" in oauth._clients

    def test_skips_registration_when_client_id_empty(self):
        oauth._clients.pop("github", None)

        init_oauth(OAuthConfig(client_id=""))

        assert "github" not in oauth._clients
