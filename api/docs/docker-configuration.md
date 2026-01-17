---
name: docker-configuration
description: Docker build configuration, security hardening, CI/CD pipeline features, and container runtime settings. Use when troubleshooting container builds, investigating signal handling issues, understanding security scanning, or modifying deployment workflows.
---

# Docker Configuration

## Overview

The application uses multi-stage Docker builds for both API and frontend services, deployed to Azure Container Apps via GitHub Actions.

## API Container (`api/Dockerfile`)

### Build Features

| Feature | Configuration | Purpose |
|---------|---------------|---------|
| BuildKit syntax | `# syntax=docker/dockerfile:1.13` | Latest BuildKit features |
| uv package manager | `COPY --from=ghcr.io/astral-sh/uv:latest` | Fast Python dependency installation |
| Python downloads disabled | `UV_PYTHON_DOWNLOADS=never` | Use system Python only |
| Bytecode compilation | `UV_COMPILE_BYTECODE=1` | Faster container startup |
| Multi-stage build | builder → runtime | Smaller final image |

### Runtime Security

| Feature | Configuration | Purpose |
|---------|---------------|---------|
| Non-root user | `USER appuser` | Principle of least privilege |
| tini init | `ENTRYPOINT ["tini", "-g", "--"]` | Proper signal handling, zombie reaping |
| Security updates | `apt-get -y upgrade` | Latest security patches |
| Fault handler | `PYTHONFAULTHANDLER=1` | C crash debugging (cairosvg/Cairo) |

### Signal Handling

The `tini` init process ensures:
- SIGTERM is properly forwarded to uvicorn workers
- Graceful shutdown completes in <1 second (vs 10s timeout without tini)
- Zombie processes are reaped correctly
- Azure Container Apps SIGTERM signals are handled properly

### Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

This is for local `docker run` testing. Azure Container Apps uses its own probes configured in Terraform (`infra/main.tf` lines 281-307).

## Frontend Container (`frontend/Dockerfile`)

### Build Optimization

Build arguments are placed after `COPY . .` to maximize cache efficiency:

```dockerfile
COPY . .
ARG VITE_API_URL
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
RUN npm run build
```

Changing build args won't invalidate the `npm ci` cache layer.

### Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1
```

## CI/CD Pipeline (`.github/workflows/deploy.yml`)

### Cache Warming

Pulls `:latest` tags before building to reuse cached layers:

```yaml
- name: Pull existing images for cache warming
  run: |
    docker pull $REGISTRY/api:latest || true
    docker pull $REGISTRY/frontend:latest || true

- name: Build and Push API Image
  run: |
    docker build \
      --cache-from=$REGISTRY/api:latest \
      --build-arg BUILDKIT_INLINE_CACHE=1 \
      ...
```

### Git Metadata Labels

Images are labeled with git commit and branch for traceability:

```yaml
--label git-commit=${{ github.sha }}
--label git-branch=${{ github.ref_name }}
```

Inspect labels on a running container:
```bash
docker inspect <image> | jq '.[0].Config.Labels'
```

### Smoke Test

After building, the API image is tested before deployment:

```yaml
- name: Smoke Test API Image
  run: |
    docker run --rm -d --name smoke-test -p 8000:8000 \
      -e DATABASE_URL=sqlite+aiosqlite:///./test.db \
      -e CLERK_SECRET_KEY=test \
      -e LLM_API_KEY=test \
      $REGISTRY/api:${{ github.sha }}
    sleep 10
    curl -f http://localhost:8000/health || (docker logs smoke-test && exit 1)
    docker stop smoke-test
```

### Security Scanning (Trivy)

Both images are scanned for HIGH and CRITICAL vulnerabilities:

```yaml
- name: Security Scan API Image
  run: |
    trivy image --ignore-unfixed --exit-code 1 --severity HIGH,CRITICAL \
      $REGISTRY/api:${{ github.sha }} || \
      echo "::warning::Trivy found vulnerabilities. Review scan results."
```

Scans warn but don't block deployments. Review warnings and address vulnerabilities promptly.

### Force Rebuild

To bypass cache and pull fresh base images (for security updates):

**Manual trigger:**
1. Go to Actions → "Deploy to Azure"
2. Click "Run workflow"
3. Set `force_rebuild` to `true`

**Programmatic:**
```bash
gh workflow run deploy.yml -f force_rebuild=true
```

## Weekly Security Rebuild (`.github/workflows/weekly-rebuild.yml`)

Runs every Sunday at 6 AM UTC to ensure security updates are applied:

```yaml
on:
  schedule:
    - cron: '0 6 * * 0'
```

This workflow:
1. Pulls fresh base images (`python:3.13-slim`, `nginx:alpine`, `node:20-alpine`)
2. Runs `apt-get upgrade` for system package updates
3. Rebuilds without cache (`--no-cache --pull`)
4. Pushes updated images to ACR

## Local Development

### Build API Image

```bash
# From repo root
docker build -f api/Dockerfile -t api-test .
```

### Run API Container

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=sqlite+aiosqlite:///./test.db \
  -e CLERK_SECRET_KEY=test \
  -e LLM_API_KEY=test \
  api-test
```

### Test Health Check

```bash
curl http://localhost:8000/health
# {"status":"healthy","service":"learn-to-cloud-api"}
```

### Test Signal Handling

```bash
# Should stop in <1 second with tini
time docker stop <container_id>
```

### Build Frontend Image

```bash
docker build \
  --build-arg VITE_API_URL=http://localhost:8000 \
  --build-arg VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxx \
  -t frontend-test ./frontend
```

### Run Trivy Locally

```bash
# Install trivy (macOS)
brew install trivy

# Scan image
trivy image api-test
trivy image --severity HIGH,CRITICAL api-test
```

## Key Files

| File | Purpose |
|------|---------|
| `api/Dockerfile` | API container build |
| `frontend/Dockerfile` | Frontend container build |
| `.github/workflows/deploy.yml` | Main CI/CD pipeline |
| `.github/workflows/weekly-rebuild.yml` | Scheduled security rebuilds |
| `infra/main.tf` | Azure Container Apps health probes (lines 281-307) |
| `.dockerignore` | Build context exclusions |

## Troubleshooting

**Container takes 10+ seconds to stop:**
- Check that tini is installed and ENTRYPOINT is configured
- Verify with: `docker inspect <image> --format '{{json .Config.Entrypoint}}'`
- Should show: `["tini","-g","--"]`

**Health check failing:**
- Check `/health` endpoint is responding
- Verify environment variables are set (DATABASE_URL, etc.)
- Check container logs: `docker logs <container>`

**Build cache not working:**
- Ensure `:latest` tag is being pushed after each build
- Check `BUILDKIT_INLINE_CACHE=1` is set
- Verify `--cache-from` points to correct registry

**Trivy scan failing:**
- Review vulnerabilities in scan output
- Check if vulnerabilities are fixable (`--ignore-unfixed` filters these)
- Update base image or dependencies as needed

**Weekly rebuild not running:**
- Check workflow is enabled in GitHub Actions
- Verify cron syntax: `0 6 * * 0` = Sunday 6 AM UTC
- Can trigger manually via workflow_dispatch
