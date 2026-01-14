"""Service layer for business logic.

Services encapsulate all business logic, keeping routes thin and focused
on HTTP handling. This separation provides:
- Clear business rules in one place
- Orchestration of multiple repositories
- Activity logging and progress tracking
- Reusable business logic across multiple endpoints

Layer hierarchy:
    Routes (HTTP) -> Services (Business Logic) -> Repositories (Database)

Services should:
- Contain all business rules and validation
- Orchestrate calls to repositories
- Return dataclasses (not ORM models) where appropriate
- Not contain HTTP-specific logic (status codes, response formatting)

Services should NOT:
- Directly execute SQL queries (use repositories)
- Know about HTTP request/response details
- Return Pydantic schema objects (routes do the conversion)
"""
