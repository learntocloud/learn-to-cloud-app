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

# Install prek (pre-commit hook runner)
if ! command -v prek &> /dev/null; then
    echo "🪝 Installing prek..."
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  TARGET="x86_64-unknown-linux-gnu" ;;
        aarch64) TARGET="aarch64-unknown-linux-gnu" ;;
        *)       echo "⚠️  Unsupported architecture: $ARCH, skipping prek install"; TARGET="" ;;
    esac
    if [ -n "$TARGET" ]; then
        curl -sSL "https://github.com/j178/prek/releases/latest/download/prek-${TARGET}.tar.gz" | tar xz --strip-components=1 -C /tmp
        install /tmp/prek /usr/local/bin/prek
        rm -f /tmp/prek
    fi
fi

# Install pre-commit hooks (--overwrite removes any legacy pre-commit hook)
echo "🪝 Installing pre-commit hooks..."
prek install --overwrite

# Copy .env.example if .env doesn't exist
if [ ! -f api/.env ] && [ -f api/.env.example ]; then
    echo "📝 Creating api/.env from .env.example..."
    cp api/.env.example api/.env
fi

echo "✅ Setup complete!"
echo ""
echo "To start developing:"
echo "  API: cd api && uv run uvicorn main:app --reload"
echo ""
echo "Note: Database migrations (alembic upgrade head) run after 'docker-compose up -d db' starts in postStartCommand."
