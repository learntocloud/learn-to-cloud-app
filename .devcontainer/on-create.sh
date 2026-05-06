#!/bin/bash
set -e

echo "🚀 Setting up Learn to Cloud development environment..."

# Install uv (skip if already installed)
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "🤖 Installing GitHub Copilot CLI + MCP servers..."
npm install -g \
    @github/copilot@latest \
    @upstash/context7-mcp@latest \
    tavily-mcp@latest \
    @azure/mcp@latest \
    mcp-remote@latest

echo "🧠 Configuring Copilot Azure skills..."
if ! copilot plugin marketplace list | grep -q "azure-skills"; then
    copilot plugin marketplace add microsoft/azure-skills
fi
if ! copilot plugin list | grep -q "azure@azure-skills"; then
    copilot plugin install azure@azure-skills
fi

# Setup Python environments. Each uv project owns its local .venv.
echo "🐍 Setting up API Python environment..."
(cd api && uv sync --locked)
echo "⚡ Setting up verification Functions Python environment..."
(cd apps/verification-functions && uv sync --locked)
echo "📦 Setting up shared package Python environment..."
(cd packages/learn-to-cloud-shared && uv sync --locked)

# Install Playwright MCP server + browser for dogfooding
echo "🎭 Installing Playwright MCP + browser..."
npm install -g @playwright/mcp@latest
if [ "$(uname -m)" = "aarch64" ]; then
    # Google Chrome has no ARM64 Linux build; use Playwright's bundled Chromium instead
    npx -y playwright install chromium
else
    npx -y playwright install chrome
fi

# Install Azure Functions Core Tools for local Durable Functions development.
if ! command -v func &> /dev/null; then
    echo "⚡ Installing Azure Functions Core Tools..."
    npm install -g azure-functions-core-tools@4 --unsafe-perm true
fi

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
