"""Clerk webhook endpoints."""

from fastapi import APIRouter, HTTPException, Request
from svix.webhooks import Webhook, WebhookVerificationError

from core import get_logger
from core.config import get_settings
from core.database import DbSession
from core.wide_event import set_wide_event_fields
from schemas import WebhookResponse
from services.webhooks_service import handle_clerk_event

logger = get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post(
    "/clerk",
    response_model=WebhookResponse,
    summary="Handle Clerk webhooks",
    description=(
        "Receives and processes Clerk webhook events for user synchronization. "
        "Validates Svix signature and handles user.created, user.updated, "
        "and user.deleted events."
    ),
    responses={
        400: {"description": "Missing webhook headers or invalid signature"},
        500: {"description": "Webhook signing secret not configured"},
    },
)
async def clerk_webhook(request: Request, db: DbSession) -> WebhookResponse:
    settings = get_settings()
    payload = await request.body()

    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Missing webhook headers")

    headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }

    if not settings.clerk_webhook_signing_secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook signing secret not configured",
        )

    try:
        wh = Webhook(settings.clerk_webhook_signing_secret)
        event = wh.verify(payload, headers)
    except WebhookVerificationError as e:
        set_wide_event_fields(
            webhook_error="verification_failed",
            webhook_svix_id=svix_id,
            webhook_error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook signature",
        )

    event_type = event.get("type") or "unknown"
    data = event.get("data", {})

    status = await handle_clerk_event(
        db,
        svix_id=svix_id,
        event_type=event_type,
        data=data,
    )

    if status == "already_processed":
        return WebhookResponse(status="already_processed")

    return WebhookResponse(status="processed", event_type=event_type)
