"""Provider-independent error data does not imply retry policy."""

import httpx2
import pytest

from learn_to_cloud.verification import deployed_api, github_http
from learn_to_cloud.verification.errors import (
    BASE_RETRIABLE,
    UpstreamResponseError,
    make_retriable,
)
from learn_to_cloud.verification.github_errors import GitHubServerError


def test_response_error_retains_only_safe_response_data():
    error = UpstreamResponseError("Unavailable", status_code=503, retry_after=2.5)
    assert str(error) == "Unavailable"
    assert vars(error) == {"status_code": 503, "retry_after": 2.5}
    assert UpstreamResponseError("Unavailable", status_code=500).retry_after is None


def test_make_retriable_preserves_explicit_network_types():
    assert BASE_RETRIABLE == (httpx2.RequestError, httpx2.TimeoutException)
    assert make_retriable() == BASE_RETRIABLE
    assert make_retriable(GitHubServerError) == (*BASE_RETRIABLE, GitHubServerError)


@pytest.mark.parametrize(
    ("module", "own_error"),
    [
        (github_http, GitHubServerError),
    ],
)
def test_retry_policies_do_not_include_base_or_other_integrations(module, own_error):
    assert own_error.__bases__ == (UpstreamResponseError,)
    assert module.RETRIABLE_EXCEPTIONS == make_retriable(own_error)
    assert not isinstance(
        UpstreamResponseError("response", status_code=503), module.RETRIABLE_EXCEPTIONS
    )
    for other in (
        GitHubServerError,
        deployed_api.DeployedApiServerError,
    ):
        assert isinstance(
            other("response", status_code=503), module.RETRIABLE_EXCEPTIONS
        ) == (other is own_error)
