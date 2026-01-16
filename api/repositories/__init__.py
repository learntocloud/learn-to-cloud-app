"""Repository layer for database operations.

Repositories encapsulate all database queries, keeping routes thin and focused
on HTTP handling. This separation provides:
- Single source of truth for database operations
- Easier testing (repositories can be mocked)
- Cleaner route code focused on request/response handling
- Reusable queries across multiple endpoints
"""

from repositories.activity import ActivityRepository
from repositories.certificate import CertificateRepository
from repositories.progress import QuestionAttemptRepository, StepProgressRepository
from repositories.submission import SubmissionRepository
from repositories.user import UserRepository

__all__ = [
    "ActivityRepository",
    "CertificateRepository",
    "QuestionAttemptRepository",
    "StepProgressRepository",
    "SubmissionRepository",
    "UserRepository",
]
