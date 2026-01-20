"""Repository layer for database operations.

Repositories encapsulate all database queries, keeping routes thin and focused
on HTTP handling. This separation provides:
- Single source of truth for database operations
- Easier testing (repositories can be mocked)
- Cleaner route code focused on request/response handling
- Reusable queries across multiple endpoints
"""

from repositories.activity_repository import ActivityRepository
from repositories.certificate_repository import CertificateRepository
from repositories.progress_repository import (
    QuestionAttemptRepository,
    StepProgressRepository,
)
from repositories.submission_repository import SubmissionRepository
from repositories.user_repository import UserRepository
from repositories.utils import log_slow_query

__all__ = [
    "ActivityRepository",
    "CertificateRepository",
    "QuestionAttemptRepository",
    "StepProgressRepository",
    "SubmissionRepository",
    "UserRepository",
    "log_slow_query",
]
