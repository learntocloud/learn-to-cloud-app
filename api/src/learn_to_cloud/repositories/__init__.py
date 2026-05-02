"""Repository layer for database operations.

Repositories encapsulate all database queries, keeping routes thin and focused
on HTTP handling. This separation provides:
- Single source of truth for database operations
- Easier testing (repositories can be mocked)
- Cleaner route code focused on request/response handling
- Reusable queries across multiple endpoints
"""

from learn_to_cloud.repositories.progress_repository import StepProgressRepository
from learn_to_cloud.repositories.submission_repository import SubmissionRepository
from learn_to_cloud.repositories.user_repository import UserRepository

__all__ = [
    "StepProgressRepository",
    "SubmissionRepository",
    "UserRepository",
]
