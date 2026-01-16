# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This is a closed-source project. All rights reserved.

## Features

- 📚 All 7 phases of the Learn to Cloud curriculum
- ✅ Progress tracking with steps, questions, and hands-on projects
- 🏆 Badges and achievements for completing phases
- 🔥 Streak tracking with forgiveness for missed days
- 📜 Certificates for phase completion
- 🔐 Authentication via Clerk
- 📊 Dashboard with progress visualization
- 🐙 GitHub integration for project submissions

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13+, FastAPI, SQLAlchemy (async), PostgreSQL |
| **Frontend** | React 19, Vite, TypeScript, Tailwind CSS v4 |
| **Auth** | Clerk |
| **Infra** | Azure Container Apps, Azure PostgreSQL, Terraform |
| **CI/CD** | GitHub Actions |

## Quick Start

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- Docker
- [Clerk](https://clerk.com) account

### Local Development

```bash
# Start database
docker-compose up -d db

# API (terminal 1)
cd api
uv sync
cp .env.example .env  # Add CLERK_SECRET_KEY
.venv/bin/python -m uvicorn main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend
npm install
cp .env.example .env.local  # Add VITE_CLERK_PUBLISHABLE_KEY
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guide.

## Project Structure

```
├── api/                  # FastAPI backend
│   ├── main.py           # App entry point
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   ├── routes/           # API endpoints
│   ├── services/         # Business logic
│   ├── repositories/     # Database queries
│   ├── core/             # Config, auth, database
│   └── tests/
├── frontend/             # React + Vite frontend
│   └── src/
│       ├── components/
│       ├── pages/
│       └── lib/          # API client, hooks
├── content/              # Phase/topic JSON content
│   └── phases/
├── infra/                # Terraform (Azure)
└── .github/
    ├── workflows/        # CI/CD
    ├── instructions/     # Copilot custom instructions
    └── skills/           # Copilot agent skills
```

## Deployment

Push to `main` triggers automated deployment via GitHub Actions → Terraform → Azure Container Apps.

## License

This project is proprietary and closed source. All rights reserved.
