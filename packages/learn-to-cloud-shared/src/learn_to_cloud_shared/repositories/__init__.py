"""Repository layer for database operations.

Repositories encapsulate all database queries, keeping routes thin and focused
on HTTP handling. This separation provides:
- Single source of truth for database operations
- Easier testing (repositories can be mocked)
- Cleaner route code focused on request/response handling
- Reusable queries across multiple endpoints
"""

from learn_to_cloud_shared.repositories.learner_step_completion_repository import (
    LearnerStepCompletionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)

__all__ = [
    "LearnerStepCompletionRepository",
    "UserRepository",
    "VerificationAttemptRepository",
]
