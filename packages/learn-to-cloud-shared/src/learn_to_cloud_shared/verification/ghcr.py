"""Anonymous GHCR manifest verification for Phase 5."""

from __future__ import annotations

from urllib.parse import quote

import httpx
from opentelemetry import trace
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.http_client import PooledClient
from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.verification.errors import make_retriable

GHCR_BASE_URL = "https://ghcr.io"
GHCR_IMAGE_NAME = "journal-api"
GHCR_IMAGE_TAG = "latest"

_MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_TASK_NAME = "Public GHCR Image"
_tracer = trace.get_tracer(__name__)


class _GhcrServerError(Exception):
    """Retriable GHCR server or rate-limit response."""


class _GhcrProtocolError(Exception):
    """GHCR returned a successful but unusable token response."""


RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = make_retriable(_GhcrServerError)


def _build_ghcr_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            get_worker_settings().http.external_api_timeout,
            connect=5.0,
        ),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


_pool = PooledClient(_build_ghcr_client)


async def _get_client() -> httpx.AsyncClient:
    return await _pool.get()


def _raise_for_transient_response(response: httpx.Response) -> None:
    if response.status_code == 429 or response.status_code >= 500:
        raise _GhcrServerError(f"GHCR returned {response.status_code}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _get_manifest_status(
    owner: str,
    client: httpx.AsyncClient,
) -> int:
    scope = f"repository:{owner}/{GHCR_IMAGE_NAME}:pull"
    token_response = await client.get(
        f"{GHCR_BASE_URL}/token",
        params={"scope": scope, "service": "ghcr.io"},
    )
    _raise_for_transient_response(token_response)
    if token_response.status_code in {401, 403, 404}:
        return token_response.status_code
    token_response.raise_for_status()

    try:
        payload = token_response.json()
    except ValueError as exc:
        raise _GhcrProtocolError("GHCR token response was not valid JSON") from exc
    token = payload.get("token") or payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise _GhcrProtocolError("GHCR token response did not include a token")

    encoded_owner = quote(owner, safe="")
    manifest_response = await client.get(
        (
            f"{GHCR_BASE_URL}/v2/{encoded_owner}/{GHCR_IMAGE_NAME}"
            f"/manifests/{GHCR_IMAGE_TAG}"
        ),
        headers={
            "Accept": _MANIFEST_ACCEPT,
            "Authorization": f"Bearer {token}",
        },
    )
    _raise_for_transient_response(manifest_response)
    return manifest_response.status_code


def _result(
    *,
    passed: bool,
    message: str,
    feedback: str,
    next_steps: str = "",
    verification_completed: bool = True,
) -> ValidationResult:
    return ValidationResult(
        is_valid=passed,
        message=message,
        verification_completed=verification_completed,
        task_results=[
            TaskResult(
                task_name=_TASK_NAME,
                passed=passed,
                feedback=feedback,
                next_steps=next_steps,
            )
        ],
    )


async def verify_public_ghcr_image(
    owner: str,
    client: httpx.AsyncClient | None = None,
) -> ValidationResult:
    """Verify the learner's public ``journal-api:latest`` manifest."""
    normalized_owner = owner.strip().lower()
    image_ref = f"ghcr.io/{normalized_owner}/{GHCR_IMAGE_NAME}:{GHCR_IMAGE_TAG}"
    client = client or await _get_client()

    with _tracer.start_as_current_span(
        "ghcr_manifest_check",
        attributes={"github.owner": normalized_owner, "container.image": image_ref},
    ) as span:
        try:
            status = await _get_manifest_status(normalized_owner, client)
        except RETRIABLE_EXCEPTIONS as exc:
            span.record_exception(exc)
            return _result(
                passed=False,
                message="Could not reach GHCR to verify the container image.",
                feedback="GHCR was temporarily unavailable.",
                next_steps="Try submitting again later.",
                verification_completed=False,
            )
        except (_GhcrProtocolError, httpx.HTTPStatusError) as exc:
            span.record_exception(exc)
            return _result(
                passed=False,
                message="GHCR returned an unexpected response.",
                feedback="Automated verification could not read the GHCR response.",
                next_steps="Try submitting again later.",
                verification_completed=False,
            )

        span.set_attribute("http.response.status_code", status)
        if status == 200:
            span.set_attribute("verification.passed", True)
            return _result(
                passed=True,
                message="The public GHCR image is pullable.",
                feedback=f"Verified public image {image_ref}.",
            )
        if status in {401, 403}:
            span.set_attribute("verification.passed", False)
            return _result(
                passed=False,
                message="The GHCR package is not publicly pullable.",
                feedback=f"Could not pull {image_ref} without authentication.",
                next_steps=(
                    "Open the journal-api package settings on GitHub, change "
                    "visibility to public, and submit again."
                ),
            )
        if status == 404:
            span.set_attribute("verification.passed", False)
            return _result(
                passed=False,
                message="The required GHCR image was not found.",
                feedback=f"No public manifest exists for {image_ref}.",
                next_steps=(
                    "Build and push journal-api with the latest tag to GHCR, "
                    "make the package public, and submit again."
                ),
            )

        span.set_attribute("verification.passed", False)
        return _result(
            passed=False,
            message="GHCR returned an unexpected response.",
            feedback=f"Automated verification received HTTP {status} from GHCR.",
            next_steps="Try submitting again later.",
            verification_completed=False,
        )
