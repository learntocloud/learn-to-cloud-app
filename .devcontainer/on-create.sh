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

# Set up the Python workspace. A single root .venv holds every member's
# dependencies, resolved from the one root uv.lock.
echo "🐍 Setting up the Python workspace environment..."
uv sync --all-packages --locked

# Install Playwright MCP server + browser for dogfooding.
echo "🎭 Installing Playwright MCP + browser..."
npm install -g @playwright/mcp@latest
# Install the browser through `playwright-mcp` rather than a standalone
# `playwright` CLI. The MCP server bundles its own playwright-core, and a
# separately installed CLI can resolve a different browser revision — the MCP
# server then reports the browser as "not installed" even though one is in the
# cache. Going through playwright-mcp keeps the revisions in lockstep.
#
# Chromium (rather than the `chrome` channel) is the only Chromium-engine
# option available on both architectures: Google Chrome has no ARM64 Linux
# build, while Playwright ships Chromium builds for both x64 and ARM64.
# Firefox and WebKit also run on both, but they would test a different engine
# than the Chromium-based browsers most users are on. This matches the
# `--browser chromium` arg in `.mcp.json` and `.vscode/mcp.json`.
#
# `--with-deps` installs the OS libraries (libatk, libnss, etc.) the browser
# needs to actually launch; without them Chromium fails with
# "error while loading shared libraries". The flag uses sudo internally.
playwright-mcp install-browser chromium --with-deps

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

echo "✅ Environment created (venv, tools installed)"
