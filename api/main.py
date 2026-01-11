"""FastAPI application for Learn to Cloud API."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from shared import (
    get_settings, async_session, init_db,
    User, ChecklistProgress, ProcessedWebhook, GitHubSubmission,
    get_user_id_from_request,
    UserResponse, ProgressItem, UserProgressResponse,
    GitHubSubmissionRequest, GitHubSubmissionResponse,
    GitHubValidationResult, PhaseGitHubRequirementsResponse,
    get_requirements_for_phase, get_requirement_by_id, validate_submission
)
from svix.webhooks import Webhook, WebhookVerificationError

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

def _build_cors_origins() -> list[str]:
    """Build CORS origins list from settings."""
    settings = get_settings()
    origins = [
        "http://localhost:3000",
        "http://localhost:4280",
    ]
    if settings.frontend_url and settings.frontend_url not in origins:
        origins.append(settings.frontend_url)
    return origins


cors_origins = _build_cors_origins()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Helper Functions ============

async def fetch_github_username_from_clerk(user_id: str) -> str | None:
    """
    Fetch GitHub username directly from Clerk API.
    This is used when the user doesn't have a github_username stored.
    """
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clerk.com/v1/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {settings.clerk_secret_key}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch user from Clerk: {response.status_code}")
                return None
            
            data = response.json()
            
            # Check external_accounts for GitHub
            external_accounts = data.get("external_accounts", [])
            for account in external_accounts:
                provider = account.get("provider", "")
                # Clerk uses "oauth_github" as the provider name
                if "github" in provider.lower():
                    username = account.get("username")
                    if username:
                        return username
            
            return None
    except Exception as e:
        logger.warning(f"Error fetching GitHub username from Clerk: {e}")
        return None


async def get_or_create_user(db, user_id: str) -> User:
    """Get user from DB or create placeholder (will be synced via webhook)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(id=user_id, email=f"{user_id}@placeholder.local")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    # If user doesn't have github_username, try to fetch it from Clerk
    if not user.github_username:
        github_username = await fetch_github_username_from_clerk(user_id)
        if github_username:
            user.github_username = github_username
            user.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(user)
    
    return user


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


# ============ Authenticated Routes ============

@app.get("/api/user/me")
async def get_current_user(user_id: str = Depends(require_auth)):
    """Get current user info."""
    async with async_session() as db:
        user = await get_or_create_user(db, user_id)
        return UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            github_username=user.github_username,
            created_at=user.created_at
        ).model_dump()


@app.get("/api/user/progress")
async def get_user_progress(user_id: str = Depends(require_auth)):
    """Get all user progress items."""
    async with async_session() as db:
        await get_or_create_user(db, user_id)
        
        result = await db.execute(
            select(ChecklistProgress).where(ChecklistProgress.user_id == user_id)
        )
        progress_items = result.scalars().all()
        
        items = [
            ProgressItem(
                checklist_item_id=p.checklist_item_id,
                is_completed=p.is_completed,
                completed_at=p.completed_at
            )
            for p in progress_items
        ]
        
        return UserProgressResponse(
            user_id=user_id,
            items=items
        ).model_dump()


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
        
        now = datetime.now(timezone.utc)
        
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


# ============ GitHub Submission Routes ============

@app.get("/api/github/requirements/{phase_id}")
async def get_phase_github_requirements(phase_id: int, user_id: str = Depends(require_auth)):
    """Get GitHub requirements and user's submissions for a phase."""
    requirements = get_requirements_for_phase(phase_id)
    
    if not requirements:
        return PhaseGitHubRequirementsResponse(
            phase_id=phase_id,
            requirements=[],
            submissions=[],
            all_validated=True  # No requirements means nothing to validate
        ).model_dump()
    
    async with async_session() as db:
        # Get user's existing submissions for this phase
        result = await db.execute(
            select(GitHubSubmission).where(
                GitHubSubmission.user_id == user_id,
                GitHubSubmission.phase_id == phase_id
            )
        )
        submissions = result.scalars().all()
        
        submission_responses = [
            GitHubSubmissionResponse(
                id=s.id,
                requirement_id=s.requirement_id,
                submission_type=s.submission_type,
                phase_id=s.phase_id,
                submitted_url=s.submitted_url,
                github_username=s.github_username,
                is_validated=s.is_validated,
                validated_at=s.validated_at,
                created_at=s.created_at
            )
            for s in submissions
        ]
        
        # Check if all requirements are validated
        validated_requirement_ids = {s.requirement_id for s in submissions if s.is_validated}
        required_ids = {r.id for r in requirements}
        all_validated = required_ids.issubset(validated_requirement_ids)
        
        return PhaseGitHubRequirementsResponse(
            phase_id=phase_id,
            requirements=requirements,
            submissions=submission_responses,
            all_validated=all_validated
        ).model_dump()


@app.post("/api/github/submit")
async def submit_github_validation(
    submission: GitHubSubmissionRequest,
    user_id: str = Depends(require_auth)
):
    """Submit a GitHub URL for validation."""
    # Get the requirement
    requirement = get_requirement_by_id(submission.requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    
    async with async_session() as db:
        # Get user with github_username
        user = await get_or_create_user(db, user_id)
        
        # For GitHub-based submissions, require GitHub username
        if requirement.submission_type.value in ("profile_readme", "repo_fork"):
            if not user.github_username:
                raise HTTPException(
                    status_code=400,
                    detail="You need to link your GitHub account to submit. Please sign out and sign in with GitHub."
                )
        
        # Validate the submission
        validation_result = await validate_submission(
            requirement=requirement,
            submitted_url=submission.submitted_url,
            expected_username=user.github_username  # Can be None for deployed apps
        )
        
        now = datetime.now(timezone.utc)
        
        # Check for existing submission
        result = await db.execute(
            select(GitHubSubmission).where(
                GitHubSubmission.user_id == user_id,
                GitHubSubmission.requirement_id == submission.requirement_id
            )
        )
        existing = result.scalar_one_or_none()
        
        # Extract username from URL for storage (only for GitHub URLs)
        from shared import parse_github_url
        parsed = parse_github_url(submission.submitted_url)
        github_username = parsed.username if parsed.is_valid else None
        
        if existing:
            # Update existing submission
            existing.submitted_url = submission.submitted_url
            existing.github_username = github_username
            existing.is_validated = validation_result.is_valid
            existing.validated_at = now if validation_result.is_valid else None
            existing.updated_at = now
            db_submission = existing
        else:
            # Create new submission
            db_submission = GitHubSubmission(
                user_id=user_id,
                requirement_id=submission.requirement_id,
                submission_type=requirement.submission_type.value,
                phase_id=requirement.phase_id,
                submitted_url=submission.submitted_url,
                github_username=github_username,
                is_validated=validation_result.is_valid,
                validated_at=now if validation_result.is_valid else None
            )
            db.add(db_submission)
        
        await db.commit()
        await db.refresh(db_submission)
        
        return GitHubValidationResult(
            is_valid=validation_result.is_valid,
            message=validation_result.message,
            username_match=validation_result.username_match,
            repo_exists=validation_result.repo_exists,
            submission=GitHubSubmissionResponse(
                id=db_submission.id,
                requirement_id=db_submission.requirement_id,
                submission_type=db_submission.submission_type,
                phase_id=db_submission.phase_id,
                submitted_url=db_submission.submitted_url,
                github_username=db_submission.github_username,
                is_validated=db_submission.is_validated,
                validated_at=db_submission.validated_at,
                created_at=db_submission.created_at
            )
        ).model_dump()


@app.get("/api/github/submissions")
async def get_user_github_submissions(user_id: str = Depends(require_auth)):
    """Get all GitHub submissions for the current user."""
    async with async_session() as db:
        result = await db.execute(
            select(GitHubSubmission).where(GitHubSubmission.user_id == user_id)
        )
        submissions = result.scalars().all()
        
        return [
            GitHubSubmissionResponse(
                id=s.id,
                requirement_id=s.requirement_id,
                submission_type=s.submission_type,
                phase_id=s.phase_id,
                submitted_url=s.submitted_url,
                github_username=s.github_username,
                is_validated=s.is_validated,
                validated_at=s.validated_at,
                created_at=s.created_at
            ).model_dump()
            for s in submissions
        ]


# ============ Webhook Routes ============

@app.post("/api/webhooks/clerk")
async def clerk_webhook(request: Request):
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


def extract_github_username(data: dict) -> str | None:
    """
    Extract GitHub username from Clerk webhook data.
    
    Clerk stores OAuth account info in 'external_accounts' array.
    Each account has 'provider' and 'username' fields.
    """
    external_accounts = data.get("external_accounts", [])
    
    for account in external_accounts:
        if account.get("provider") == "github" or account.get("provider") == "oauth_github":
            # Try different possible field names
            username = account.get("username") or account.get("provider_user_id")
            if username:
                return username
    
    return None


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
    
    # Extract GitHub username from OAuth accounts
    github_username = extract_github_username(data)
    
    if existing_user:
        existing_user.email = primary_email
        existing_user.first_name = data.get("first_name")
        existing_user.last_name = data.get("last_name")
        existing_user.avatar_url = data.get("image_url")
        existing_user.github_username = github_username
        existing_user.updated_at = datetime.now(timezone.utc)
    else:
        user = User(
            id=user_id,
            email=primary_email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
            github_username=github_username,
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
    
    # Extract GitHub username from OAuth accounts
    github_username = extract_github_username(data)
    
    user.email = primary_email
    user.first_name = data.get("first_name")
    user.last_name = data.get("last_name")
    user.avatar_url = data.get("image_url")
    user.github_username = github_username
    user.updated_at = datetime.now(timezone.utc)


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
        user.updated_at = datetime.now(timezone.utc)
