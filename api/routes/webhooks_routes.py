"""Clerk webhook endpoints."""

from fastapi import APIRouter, HTTPException, Request
from svix.webhooks import Webhook, WebhookVerificationError

from core import get_logger
from core.config import get_settings
from core.database import DbSession
from schemas import WebhookResponse
from services.webhooks_service import handle_clerk_event

logger = get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/clerk", response_model=WebhookResponse)
async def clerk_webhook(request: Request, db: DbSession) -> WebhookResponse:
    """Handle Clerk webhooks for user sync."""
    settings = get_settings()
    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id"),
        "svix-timestamp": request.headers.get("svix-timestamp"),
        "svix-signature": request.headers.get("svix-signature"),
    }

    if not all(headers.values()):
        raise HTTPException(status_code=400, detail="Missing webhook headers")

    verified_headers = {k: v for k, v in headers.items() if v is not None}

    if not settings.clerk_webhook_signing_secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook signing secret not configured",
        )

    try:
        wh = Webhook(settings.clerk_webhook_signing_secret)
        event = wh.verify(payload, verified_headers)
    except WebhookVerificationError as e:
        logger.warning(
            f"Webhook verification failed: svix_id={headers.get('svix-id')}, "
            f"timestamp={headers.get('svix-timestamp')}, error={e}"
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook signature",
        )

    event_type = event.get("type") or "unknown"
    data = event.get("data", {})
    svix_id = verified_headers["svix-id"]

    status = await handle_clerk_event(
        db,
        svix_id=svix_id,
        event_type=event_type,
        data=data,
    )

    if status == "already_processed":
        return WebhookResponse(status="already_processed")

    return WebhookResponse(status="processed", event_type=event_type)
