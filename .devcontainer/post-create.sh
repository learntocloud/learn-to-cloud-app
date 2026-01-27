#!/bin/bash
set -e

echo "🚀 Setting up Learn to Cloud development environment..."

# Install uv (skip if already installed)
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# Setup API (Python/FastAPI)
echo "🐍 Setting up API..."
cd api
# Remove existing venv to avoid interactive prompt
rm -rf .venv
uv venv
uv sync
cd ..

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
uvx pre-commit install

# Setup Frontend (Vite)
echo "⚛️ Setting up Frontend..."
cd frontend
npm install
cd ..

# Copy .env.example files if .env doesn't exist
if [ ! -f api/.env ] && [ -f api/.env.example ]; then
    echo "📝 Creating api/.env from .env.example..."
    cp api/.env.example api/.env
fi

if [ ! -f frontend/.env.local ] && [ -f frontend/.env.example ]; then
    echo "📝 Creating frontend/.env.local from .env.example..."
    cp frontend/.env.example frontend/.env.local
fi

# Run database migrations
echo "🗄️ Running database migrations..."
cd api
.venv/bin/alembic upgrade head
cd ..

echo "✅ Setup complete!"
echo ""
echo "To start developing:"
echo "  API:      cd api && uv run uvicorn main:app --reload"
echo "  Frontend: cd frontend && npm run dev"
