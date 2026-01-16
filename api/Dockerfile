# syntax=docker/dockerfile:1.14
# Build stage - compile dependencies
# Build context should be repo root: docker build -f api/Dockerfile -t api .
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for caching
COPY api/pyproject.toml ./

# Install dependencies to virtual environment
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv venv /app/.venv && \
    uv sync --no-dev

# Production stage - minimal runtime
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install Cairo library for PDF generation (required by cairosvg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libcairo2 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Set content directory for Docker
ENV CONTENT_DIR="/app/content/phases"

# Copy application code from api/
COPY --chown=appuser:appuser api/ .

# Copy content from repo root
COPY --chown=appuser:appuser content /app/content

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run with multiple workers for better concurrency
# Workers = 2-4 x CPU cores, but Container Apps typically has 0.5-2 vCPU
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
