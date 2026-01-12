# Local Development Setup

This guide covers how to set up the Learn to Cloud app for local development.

## Quick Start (Dev Container - Recommended)

The fastest way to get started is using VS Code Dev Containers. Everything is pre-configured.

### Prerequisites

- [VS Code](https://code.visualstudio.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/madebygps/learn-to-cloud-app.git
   cd learn-to-cloud-app
   ```

2. **Open in Dev Container**
   - Open the folder in VS Code
   - Press `F1` → "Dev Containers: Reopen in Container"
   - Wait for the container to build (first time takes a few minutes)

3. **Configure environment variables**
   
   The API `.env` file is auto-created from `.env.example`. You need to add your Clerk keys:
   
   ```bash
   # Edit api/.env and add your Clerk keys:
   CLERK_SECRET_KEY=sk_test_your_key_here
   ```
   
   Create the frontend environment file:
   ```bash
   cp frontend/.env.local.example frontend/.env.local
   # Edit frontend/.env.local and add your Clerk keys
   ```

4. **Start the application**
   
   Use VS Code's Run and Debug panel (`Ctrl+Shift+D` / `Cmd+Shift+D`):
   
   - **Full Stack: API + Frontend** - Starts both services
   - **API: FastAPI (uvicorn)** - Backend only (port 8000)
   - **Frontend: Next.js** - Frontend only (port 3000)

5. **Access the app**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## What Happens Automatically

When the Dev Container starts:

| Step | What Happens |
|------|--------------|
| `postCreateCommand` | Installs Python (uv) and Node.js dependencies |
| `postStartCommand` | Starts PostgreSQL database via Docker Compose |
| Port forwarding | Ports 3000, 5432, 8000 are automatically forwarded |

## Manual Setup (Without Dev Container)

If you prefer to run locally without containers:

### Prerequisites

- Python 3.13+
- Node.js 20+
- PostgreSQL 16+
- [uv](https://docs.astral.sh/uv/) - Python package manager

### 1. Start PostgreSQL

Using Docker:
```bash
docker-compose up -d db
```

Or install PostgreSQL locally and create a database:
```sql
CREATE DATABASE learn_to_cloud;
```

### 2. Backend Setup

```bash
cd api

# Create virtual environment and install dependencies
uv venv
uv sync

# Copy environment variables
cp .env.example .env

# Edit .env with your settings (see Environment Variables section)

# Run the API
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment variables
cp .env.local.example .env.local

# Edit .env.local with your Clerk keys

# Run the frontend
npm run dev
```

## Environment Variables

### Backend (`api/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/learn_to_cloud` |
| `CLERK_SECRET_KEY` | Clerk secret key (required) | - |
| `CLERK_WEBHOOK_SIGNING_SECRET` | For Clerk webhooks | - |
| `ENVIRONMENT` | `dev` or `production` | `dev` |
| `GITHUB_TOKEN` | GitHub API token (optional, for higher rate limits) | - |
| `FRONTEND_URL` | Frontend URL for CORS | `http://localhost:3000` |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key |
| `NEXT_PUBLIC_API_URL` | Backend API URL (`http://localhost:8000`) |

## Setting Up Clerk

1. Create a free account at [clerk.com](https://clerk.com)
2. Create a new application
3. Get your API keys from the dashboard:
   - **Publishable Key** (`pk_test_...`) → Frontend
   - **Secret Key** (`sk_test_...`) → Both frontend and backend
4. (Optional) Set up webhooks for user sync:
   - Endpoint: `http://localhost:8000/api/webhooks/clerk`
   - Events: `user.created`, `user.updated`, `user.deleted`

## Database

### Default Credentials (Docker Compose)

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `learn_to_cloud` |
| Username | `postgres` |
| Password | `postgres` |

### Connection String

```
postgresql+asyncpg://postgres:postgres@localhost:5432/learn_to_cloud
```

### Reset Database

To drop and recreate all tables, set in `api/.env`:
```
RESET_DB_ON_STARTUP=true
```

Then restart the API. **Warning:** This deletes all data!

## Troubleshooting

### "Connection refused" errors

The PostgreSQL database isn't running. Start it with:
```bash
docker-compose up -d db
```

### "Unauthorized" errors

- Check that `CLERK_SECRET_KEY` is set in `api/.env`
- Ensure you're signed in on the frontend
- Verify the Clerk keys match between frontend and backend projects

### Database connection issues

Verify the `DATABASE_URL` in `api/.env` matches your PostgreSQL setup:
- Docker Compose default: `postgres:postgres@localhost:5432/learn_to_cloud`
- Check the database exists and is accessible

### Port already in use

If port 8000 or 3000 is in use, find and kill the process:
```bash
# Find process using port
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Frontend can't reach API

- Ensure `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`
- Verify the API is running and healthy: `curl http://localhost:8000/health`

## VS Code Launch Configurations

The project includes pre-configured debug configurations:

| Configuration | Description |
|--------------|-------------|
| **Full Stack: API + Frontend** | Starts both services with debugging |
| **API: FastAPI (uvicorn)** | Backend only with hot reload |
| **Frontend: Next.js** | Frontend with browser auto-open |
| **Frontend: Next.js (Server-side)** | Frontend with server-side debugging |

Access via Run and Debug panel (`Ctrl+Shift+D` / `Cmd+Shift+D`).
