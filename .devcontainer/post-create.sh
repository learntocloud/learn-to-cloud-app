#!/bin/bash
set -e

export PATH="$HOME/.local/bin:$PATH"

# Install pre-commit hooks (--overwrite removes any legacy pre-commit hook)
echo "🪝 Installing pre-commit hooks..."
prek install --overwrite

# Copy .env.example if .env doesn't exist
if [ ! -f api/.env ] && [ -f api/.env.example ]; then
    echo "📝 Creating api/.env from .env.example..."
    cp api/.env.example api/.env
fi

# Ensure DATABASE_URL uses the devcontainer Docker network hostname (db:5432).
# This fixes stale .env files that point to localhost instead of the db service.
if [ -f api/.env ] && ! grep -q "^DATABASE_URL=.*@db:5432/" api/.env; then
    echo "📝 Updating DATABASE_URL to devcontainer DB host (db:5432)..."
    sed -i 's|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/learn_to_cloud|' api/.env
fi

# Ensure DEBUG=true is in .env for local development
if [ -f api/.env ] && ! grep -q "^DEBUG=true" api/.env; then
    echo "📝 Adding DEBUG=true to api/.env..."
    # printf ensures a leading newline in case the file doesn't end with one
    printf '\nDEBUG=true\n' >> api/.env
fi

# Run database migrations
echo "🗄️  Running database migrations..."
cd api && uv run alembic upgrade head && cd ..

echo "✅ Setup complete!"
echo ""
echo "To start developing:"
echo "  API: cd api && uv run uvicorn main:app --reload"
echo ""
echo "Note: Database is provisioned by docker-compose (PostgreSQL on port 54320)."
