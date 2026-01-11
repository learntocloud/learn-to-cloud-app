# Learn to Cloud App

A web application for tracking your progress through the [Learn to Cloud](https://learntocloud.guide) guide.

> **Note:** This is a closed-source project. All rights reserved.

## Features

- 📚 All 6 phases of the Learn to Cloud curriculum
- ✅ Progress tracking for topics and checklist items
- 🔐 Authentication via Clerk
- 📊 Dashboard with overall progress visualization
- ☁️ Deployable to Azure (Azure Functions + Static Web Apps + PostgreSQL)

## Tech Stack

### Backend
- **Python 3.13+** with **Azure Functions** (v2 programming model)
- **SQLAlchemy** (async) for database ORM
- **PostgreSQL** (production) / **SQLite** (development)
- **Clerk** for authentication
- **uv** for package management

### Frontend
- **Next.js 16** with App Router
- **TypeScript**
- **Tailwind CSS v4**
- **Clerk** for authentication UI

### Infrastructure
- **Azure Functions** (Flex Consumption) - Backend API
- **Azure Static Web Apps** - Frontend hosting with linked backend
- **Azure Database for PostgreSQL** (Flexible Server) - Production database
- **Azure Application Insights** - Monitoring

## Local Development

### Prerequisites
- Python 3.13+
- Node.js 20+
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) v4
- [uv](https://docs.astral.sh/uv/) - Python package manager
- [Clerk](https://clerk.com) account

### 1. Backend setup (Azure Functions)

```bash
cd api

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv sync

# Edit local.settings.json with your Clerk keys

# Run Azure Functions locally
func host start --port 7071
```

Backend will be available at http://localhost:7071/api

### 3. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment variables
cp .env.example .env.local
# Edit .env.local with your Clerk keys

# Run development server
npm run dev
```

Frontend will be available at http://localhost:3000

### 3. Configure Clerk

1. Create a Clerk application at https://dashboard.clerk.com
2. Get your API keys:
   - `CLERK_SECRET_KEY` (backend)
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (frontend)
3. Set up webhook:
   - Endpoint: `http://localhost:7071/api/webhooks/clerk`
   - Events: `user.created`, `user.updated`, `user.deleted`
   - Get `CLERK_WEBHOOK_SIGNING_SECRET`

## Azure Deployment

### Option 1: Using Azure Developer CLI (Recommended)

```bash
# Login to Azure
azd auth login

# Initialize environment (first time only)
azd init

# Provision infrastructure and deploy
azd up
```

You'll be prompted for secure parameters (PostgreSQL password, Clerk keys).

### Option 2: Manual Bicep Deployment

```bash
cd infra

az deployment sub create \
  --location eastus \
  --template-file main.bicep \
  --parameters \
    environment=dev \
    postgresAdminPassword='<secure-password>' \
    clerkSecretKey='<your-clerk-secret>' \
    clerkWebhookSigningSecret='<your-webhook-secret>' \
    clerkPublishableKey='<your-publishable-key>'
```

Then deploy the apps:

```bash
# Deploy frontend
cd frontend && npx swa deploy --env production

# Deploy API
cd api && func azure functionapp publish <function-app-name>
```

## API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/` | Health check | No |
| GET | `/api/phases` | List all phases | No |
| GET | `/api/phases/{id}` | Get phase by ID | No |
| GET | `/api/p/{slug}` | Get phase by slug | No |
| GET | `/api/p/{phase}/{topic}` | Get topic by slug | No |
| GET | `/api/user/phases` | Phases with progress | Yes |
| GET | `/api/user/p/{slug}` | Phase with full progress | Yes |
| GET | `/api/user/p/{phase}/{topic}` | Topic with progress | Yes |
| GET | `/api/user/dashboard` | User dashboard data | Yes |
| POST | `/api/checklist/{id}/toggle` | Toggle checklist item | Yes |
| POST | `/api/webhooks/clerk` | Clerk webhook handler | Svix |

## Project Structure

```
learn-to-cloud-app/
├── api/
│   ├── function_app.py      # Azure Functions endpoints
│   ├── host.json            # Functions host config
│   ├── requirements.txt     # Python dependencies
│   ├── pyproject.toml       # uv project config
│   └── shared/
│       ├── __init__.py      # Module exports
│       ├── auth.py          # Clerk authentication
│       ├── config.py        # Settings
│       ├── content.py       # Static phase content
│       ├── database.py      # DB connection
│       ├── models.py        # SQLAlchemy models
│       └── schemas.py       # Pydantic schemas
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router pages
│   │   ├── components/      # React components
│   │   ├── lib/             # API client, types, hooks
│   │   └── proxy.ts         # Clerk auth proxy (Next.js 16)
│   ├── staticwebapp.config.json
│   └── package.json
├── infra/
│   ├── main.bicep           # Subscription-level deployment
│   └── resources.bicep      # Resource definitions
└── azure.yaml               # Azure Developer CLI config
```

## License

This project is proprietary and closed source. All righazd upts reserved.
