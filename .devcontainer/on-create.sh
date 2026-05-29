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
# Best-effort: configuring Copilot plugins must never abort the whole
# devcontainer setup. If a step fails (for example, the Copilot CLI is not
# logged in yet), warn and continue so the rest of on-create still runs.
if ! copilot plugin marketplace list 2>/dev/null | grep -q "azure-skills"; then
    copilot plugin marketplace add microsoft/azure-skills \
        || echo "⚠️  Could not add the azure-skills marketplace; skipping. Run 'copilot plugin marketplace add microsoft/azure-skills' manually later."
fi
if ! copilot plugin list 2>/dev/null | grep -q "azure@azure-skills"; then
    copilot plugin install azure@azure-skills \
        || echo "⚠️  Could not install the azure-skills plugin; skipping. Run 'copilot plugin install azure@azure-skills' manually later."
fi

# Setup Python environments. Each uv project owns its local .venv.
echo "🐍 Setting up API Python environment..."
(cd api && uv sync --locked)
echo "⚡ Setting up verification Functions Python environment..."
(cd apps/verification-functions && uv sync --locked)
echo "📦 Setting up shared package Python environment..."
(cd packages/learn-to-cloud-shared && uv sync --locked)

# Install Playwright MCP server + browser for dogfooding.
# Install `playwright` globally alongside the MCP package so the subsequent
# `playwright install` call doesn't emit the "install your project's
# dependencies first" warning (npx looks for playwright in the cwd's
# package.json, and the repo root has none).
echo "🎭 Installing Playwright MCP + browser..."
npm install -g playwright @playwright/mcp@latest
# `--with-deps` installs the OS libraries (libatk, libnss, etc.) the browser
# needs to actually launch; without them Chromium/Chrome fail with
# "error while loading shared libraries". The flag uses sudo internally.
if [ "$(uname -m)" = "aarch64" ]; then
    # Google Chrome has no ARM64 Linux build; use Playwright's bundled Chromium instead
    playwright install --with-deps chromium
else
    playwright install --with-deps chrome
fi

# Install Aspire CLI for the MCP server (aspire agent mcp).
# Installed via the standalone script so we don't need .NET SDK or the VS Code
# extension (which pulls in C# DevKit and .NET Installer as dependencies).
if ! command -v aspire &> /dev/null; then
    echo "🌐 Installing Aspire CLI..."
    curl -sSL https://aspire.dev/install.sh | bash
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

# Install Firecrawl CLI + agent skills for web scraping/search.
echo "🔥 Installing Firecrawl CLI + skills..."
npm install -g firecrawl-cli@latest
firecrawl init --all -y --skip-install 2>/dev/null || true

echo "✅ Environment created (venv, tools installed)"
