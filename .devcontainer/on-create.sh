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
uv sync
cd ..

# Install Playwright MCP server + Chrome for dogfooding
echo "🎭 Installing Playwright MCP + Chrome..."
npm install -g @playwright/mcp@latest
npx -y playwright install chrome

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
        sudo install /tmp/prek /usr/local/bin/prek
        rm -f /tmp/prek
    fi
fi

echo "✅ Environment created (venv, tools installed)"
