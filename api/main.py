"""FastAPI application for Learn to Cloud API."""

import json
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from shared import (
    get_settings, async_session, init_db,
    User, ChecklistProgress, ProcessedWebhook, CompletionStatus,
    get_user_id_from_request,
    get_all_phases, get_phase_by_id, get_phase_by_slug, get_topic_by_slug,
    Phase, PhaseWithProgress, PhaseDetailWithProgress, PhaseProgress,
    TopicWithProgress, ChecklistItemWithProgress, TopicChecklistItemWithProgress,
    DashboardResponse, UserResponse
)
from svix.webhooks import Webhook, WebhookVerificationError

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan
)

# Build CORS origins list
cors_origins = [
    "http://localhost:3000",
    "http://localhost:4280",
]

# Add frontend URL from environment
if settings.frontend_url:
    cors_origins.append(settings.frontend_url)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Helper Functions ============

async def get_or_create_user(db, user_id: str) -> User:
    """Get user from DB or create placeholder (will be synced via webhook)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(id=user_id, email=f"{user_id}@placeholder.local")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    return user


def calculate_phase_progress(
    phase_id: int,
    checklist_progress: list[ChecklistProgress],
    total_phase_checklist: int,
    total_topic_checklist: int
) -> PhaseProgress:
    """Calculate progress for a phase based on all checklist items."""
    phase_checklist_completed = sum(
        1 for c in checklist_progress 
        if c.is_completed and "topic" not in c.checklist_item_id
    )
    topic_checklist_completed = sum(
        1 for c in checklist_progress 
        if c.is_completed and "topic" in c.checklist_item_id
    )
    
    total_completed = phase_checklist_completed + topic_checklist_completed
    total_items = total_phase_checklist + total_topic_checklist
    percentage = (total_completed / total_items * 100) if total_items > 0 else 0
    
    if total_completed == 0:
        status = CompletionStatus.NOT_STARTED
    elif total_completed == total_items:
        status = CompletionStatus.COMPLETED
    else:
        status = CompletionStatus.IN_PROGRESS
    
    return PhaseProgress(
        phase_id=phase_id,
        checklist_completed=total_completed,
        checklist_total=total_items,
        percentage=round(percentage, 1),
        status=status
    )


async def get_current_user_id(request: Request) -> str | None:
    """Extract user ID from request headers."""
    return get_user_id_from_request(request)


async def require_auth(request: Request) -> str:
    """Require authentication and return user ID."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


# ============ Health Check ============

@app.get("/")
@app.get("/api")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "learn-to-cloud-api"}


# ============ Public Routes (no auth) ============

@app.get("/api/phases")
async def list_phases():
    """Get all phases (public, no progress)."""
    phases = get_all_phases()
    return [p.model_dump() for p in phases]


@app.get("/api/phases/{phase_id}")
async def get_phase(phase_id: int):
    """Get a single phase by ID (public, no progress)."""
    phase = get_phase_by_id(phase_id)
    if not phase:
        raise HTTPException(status_code=404, detail="Phase not found")
    return phase.model_dump()


@app.get("/api/p/{phase_slug}")
async def get_phase_by_slug_route(phase_slug: str):
    """Get a single phase by slug (public, no progress)."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        raise HTTPException(status_code=404, detail="Phase not found")
    return phase.model_dump()


@app.get("/api/p/{phase_slug}/{topic_slug}")
async def get_topic_by_slug_route(phase_slug: str, topic_slug: str):
    """Get a single topic by phase and topic slug (public, no progress)."""
    topic = get_topic_by_slug(phase_slug, topic_slug)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic.model_dump()


# ============ Authenticated Routes ============

@app.get("/api/user/phases")
async def list_phases_with_progress(user_id: str = Depends(require_auth)):
    """Get all phases with user's progress."""
    async with async_session() as db:
        await get_or_create_user(db, user_id)
        phases = get_all_phases()
        
        checklist_result = await db.execute(
            select(ChecklistProgress).where(ChecklistProgress.user_id == user_id)
        )
        all_checklist_progress = checklist_result.scalars().all()
        
        phases_with_progress = []
        for phase in phases:
            phase_checklist_progress = [c for c in all_checklist_progress if c.phase_id == phase.id]
            total_topic_checklist = sum(len(topic.checklist) for topic in phase.topics)
            
            progress = calculate_phase_progress(
                phase.id,
                phase_checklist_progress,
                len(phase.checklist),
                total_topic_checklist
            )
            
            phases_with_progress.append(PhaseWithProgress(
                **phase.model_dump(),
                progress=progress
            ))
        
        return [p.model_dump() for p in phases_with_progress]


@app.get("/api/user/p/{phase_slug}")
async def get_phase_with_progress_by_slug(phase_slug: str, user_id: str = Depends(require_auth)):
    """Get a single phase by slug with full topic and checklist progress."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        raise HTTPException(status_code=404, detail="Phase not found")
    
    async with async_session() as db:
        await get_or_create_user(db, user_id)
        
        checklist_result = await db.execute(
            select(ChecklistProgress).where(
                ChecklistProgress.user_id == user_id,
                ChecklistProgress.phase_id == phase.id
            )
        )
        checklist_progress_map = {c.checklist_item_id: c for c in checklist_result.scalars().all()}
        
        topics_with_progress = []
        for topic in phase.topics:
            topic_checklist_with_progress = []
            for item in topic.checklist:
                progress = checklist_progress_map.get(item.id)
                topic_checklist_with_progress.append(TopicChecklistItemWithProgress(
                    id=item.id,
                    text=item.text,
                    order=item.order,
                    is_completed=progress.is_completed if progress else False,
                    completed_at=progress.completed_at if progress else None
                ))
            
            topic_items_completed = sum(1 for c in topic_checklist_with_progress if c.is_completed)
            topic_total_items = len(topic.checklist)
            
            topics_with_progress.append(TopicWithProgress(
                id=topic.id,
                name=topic.name,
                slug=topic.slug,
                description=topic.description,
                order=topic.order,
                estimated_time=topic.estimated_time,
                learning_steps=topic.learning_steps,
                checklist=topic_checklist_with_progress,
                is_capstone=topic.is_capstone,
                items_completed=topic_items_completed,
                items_total=topic_total_items
            ))
        
        checklist_with_progress = []
        for item in phase.checklist:
            progress = checklist_progress_map.get(item.id)
            checklist_with_progress.append(ChecklistItemWithProgress(
                **item.model_dump(),
                is_completed=progress.is_completed if progress else False,
                completed_at=progress.completed_at if progress else None
            ))
        
        total_topic_checklist = sum(len(topic.checklist) for topic in phase.topics)
        phase_progress = calculate_phase_progress(
            phase.id,
            list(checklist_progress_map.values()),
            len(phase.checklist),
            total_topic_checklist
        )
        
        result = PhaseDetailWithProgress(
            id=phase.id,
            name=phase.name,
            slug=phase.slug,
            description=phase.description,
            estimated_weeks=phase.estimated_weeks,
            order=phase.order,
            prerequisites=phase.prerequisites,
            topics=topics_with_progress,
            checklist=checklist_with_progress,
            progress=phase_progress
        )
        
        return result.model_dump()


@app.get("/api/user/p/{phase_slug}/{topic_slug}")
async def get_topic_with_progress_by_slug(phase_slug: str, topic_slug: str, user_id: str = Depends(require_auth)):
    """Get a single topic by slug with checklist progress."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        raise HTTPException(status_code=404, detail="Phase not found")
    
    topic = get_topic_by_slug(phase_slug, topic_slug)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    async with async_session() as db:
        await get_or_create_user(db, user_id)
        
        checklist_result = await db.execute(
            select(ChecklistProgress).where(
                ChecklistProgress.user_id == user_id,
                ChecklistProgress.phase_id == phase.id
            )
        )
        checklist_progress_map = {c.checklist_item_id: c for c in checklist_result.scalars().all()}
        
        topic_checklist_with_progress = []
        for item in topic.checklist:
            progress = checklist_progress_map.get(item.id)
            topic_checklist_with_progress.append(TopicChecklistItemWithProgress(
                id=item.id,
                text=item.text,
                order=item.order,
                is_completed=progress.is_completed if progress else False,
                completed_at=progress.completed_at if progress else None
            ))
        
        topic_items_completed = sum(1 for c in topic_checklist_with_progress if c.is_completed)
        topic_total_items = len(topic.checklist)
        
        result = TopicWithProgress(
            id=topic.id,
            name=topic.name,
            slug=topic.slug,
            description=topic.description,
            order=topic.order,
            estimated_time=topic.estimated_time,
            learning_steps=topic.learning_steps,
            checklist=topic_checklist_with_progress,
            is_capstone=topic.is_capstone,
            items_completed=topic_items_completed,
            items_total=topic_total_items
        )
        
        return result.model_dump()


@app.post("/api/checklist/{item_id}/toggle")
async def toggle_checklist_item(item_id: str, user_id: str = Depends(require_auth)):
    """Toggle a checklist item completion status."""
    try:
        phase_id = int(item_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid checklist item ID format")
    
    async with async_session() as db:
        await get_or_create_user(db, user_id)
        
        result = await db.execute(
            select(ChecklistProgress).where(
                ChecklistProgress.user_id == user_id,
                ChecklistProgress.checklist_item_id == item_id
            )
        )
        progress = result.scalar_one_or_none()
        
        now = datetime.utcnow()
        
        if not progress:
            progress = ChecklistProgress(
                user_id=user_id,
                checklist_item_id=item_id,
                phase_id=phase_id,
                is_completed=True,
                completed_at=now
            )
            db.add(progress)
            is_completed = True
        else:
            progress.is_completed = not progress.is_completed
            progress.completed_at = now if progress.is_completed else None
            is_completed = progress.is_completed
        
        await db.commit()
        return {"success": True, "item_id": item_id, "is_completed": is_completed}


@app.get("/api/user/dashboard")
async def get_dashboard(user_id: str = Depends(require_auth)):
    """Get user dashboard with overall progress."""
    async with async_session() as db:
        user = await get_or_create_user(db, user_id)
        phases = get_all_phases()
        
        checklist_result = await db.execute(
            select(ChecklistProgress).where(ChecklistProgress.user_id == user_id)
        )
        all_checklist_progress = checklist_result.scalars().all()
        
        phases_with_progress = []
        total_items = 0
        total_completed = 0
        current_phase = None
        
        for phase in phases:
            phase_checklist_progress = [c for c in all_checklist_progress if c.phase_id == phase.id]
            total_topic_checklist = sum(len(topic.checklist) for topic in phase.topics)
            
            progress = calculate_phase_progress(
                phase.id,
                phase_checklist_progress,
                len(phase.checklist),
                total_topic_checklist
            )
            
            phases_with_progress.append(PhaseWithProgress(
                **phase.model_dump(),
                progress=progress
            ))
            
            total_items += progress.checklist_total
            total_completed += progress.checklist_completed
            
            if current_phase is None and progress.status != CompletionStatus.COMPLETED:
                current_phase = phase.id
        
        overall_progress = (total_completed / total_items * 100) if total_items > 0 else 0
        
        result = DashboardResponse(
            user=UserResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                avatar_url=user.avatar_url,
                created_at=user.created_at
            ),
            phases=phases_with_progress,
            overall_progress=round(overall_progress, 1),
            total_completed=total_completed,
            total_items=total_items,
            current_phase=current_phase
        )
        
        return result.model_dump()


# ============ Webhook Routes ============

@app.post("/api/webhooks/clerk")
async def clerk_webhook(request: Request):
    """Handle Clerk webhooks for user sync."""
    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id"),
        "svix-timestamp": request.headers.get("svix-timestamp"),
        "svix-signature": request.headers.get("svix-signature"),
    }
    
    if not all(headers.values()):
        raise HTTPException(status_code=400, detail="Missing webhook headers")
    
    if not settings.clerk_webhook_signing_secret:
        raise HTTPException(status_code=500, detail="Webhook signing secret not configured")
    
    try:
        wh = Webhook(settings.clerk_webhook_signing_secret)
        event = wh.verify(payload, headers)
    except WebhookVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {str(e)}")
    
    event_type = event.get("type")
    data = event.get("data", {})
    svix_id = headers["svix-id"]
    
    async with async_session() as db:
        result = await db.execute(
            select(ProcessedWebhook).where(ProcessedWebhook.id == svix_id)
        )
        if result.scalar_one_or_none():
            return {"status": "already_processed"}
        
        if event_type == "user.created":
            await handle_user_created(db, data)
        elif event_type == "user.updated":
            await handle_user_updated(db, data)
        elif event_type == "user.deleted":
            await handle_user_deleted(db, data)
        
        processed = ProcessedWebhook(id=svix_id, event_type=event_type)
        db.add(processed)
        await db.commit()
    
    return {"status": "processed", "event_type": event_type}


async def handle_user_created(db, data: dict):
    """Handle user.created webhook event."""
    user_id = data.get("id")
    if not user_id:
        return
    
    result = await db.execute(select(User).where(User.id == user_id))
    existing_user = result.scalar_one_or_none()
    
    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (e.get("email_address") for e in email_addresses if e.get("id") == data.get("primary_email_address_id")),
        email_addresses[0].get("email_address") if email_addresses else f"{user_id}@unknown.local"
    )
    
    if existing_user:
        existing_user.email = primary_email
        existing_user.first_name = data.get("first_name")
        existing_user.last_name = data.get("last_name")
        existing_user.avatar_url = data.get("image_url")
        existing_user.updated_at = datetime.utcnow()
    else:
        user = User(
            id=user_id,
            email=primary_email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
        )
        db.add(user)


async def handle_user_updated(db, data: dict):
    """Handle user.updated webhook event."""
    user_id = data.get("id")
    if not user_id:
        return
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        await handle_user_created(db, data)
        return
    
    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (e.get("email_address") for e in email_addresses if e.get("id") == data.get("primary_email_address_id")),
        email_addresses[0].get("email_address") if email_addresses else user.email
    )
    
    user.email = primary_email
    user.first_name = data.get("first_name")
    user.last_name = data.get("last_name")
    user.avatar_url = data.get("image_url")
    user.updated_at = datetime.utcnow()


async def handle_user_deleted(db, data: dict):
    """Handle user.deleted webhook event."""
    user_id = data.get("id")
    if not user_id:
        return
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user:
        user.email = f"deleted_{user_id}@deleted.local"
        user.first_name = None
        user.last_name = None
        user.avatar_url = None
        user.updated_at = datetime.utcnow()
