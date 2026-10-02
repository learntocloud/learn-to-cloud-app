"""Every outbound dependency must go through the shared measured boundary.

A library switch (such as authlib moving from httpx to httpx2) or a new client
constructed outside the factories below would silently produce untraced,
unmeasured calls, so both are rejected until they are reviewed here.
"""

import ast
import re
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_FILES = sorted((_ROOT / "src/learn_to_cloud").rglob("*.py"))

_NETWORK_PACKAGE = re.compile(
    r"http|request|url|aio|grpc|socket|websocket|pg|psycopg|sql|redis|mongo"
    r"|openai|anthropic|boto|kafka|amqp|mqtt|ftp|smtp|ldap|azure|google|client|sdk"
)

# Every locked package that can open network connections, and how it is covered.
_NETWORK_PACKAGES = {
    "httpx": "GitHub and deployed APIs via MeasuredTransport; openai's client is "
    "traced by HTTPXClientInstrumentor and measured by outbound_call",
    "httpcore": "httpx internals",
    "httpx2": "authlib GitHub OAuth via _MeasuredOAuthTransport",
    "httpcore2": "httpx2 internals",
    "httpx2-jsfetch": "httpx2 browser backend, unused on CPython",
    "aiohttp": "azure-core async transport for Entra tokens, via MeasuredCredential",
    "aiohappyeyeballs": "aiohttp internals",
    "aiosignal": "aiohttp internals",
    "azure-core": "azure SDK pipeline, traced by azure-core-tracing-opentelemetry",
    "azure-core-tracing-opentelemetry": "azure SDK tracing plugin",
    "azure-identity": "Entra credentials, wrapped in MeasuredCredential",
    "azure-ai-inference": "agent-framework-foundry dependency, not called directly",
    "azure-ai-projects": "agent-framework-foundry dependency, not called directly",
    "azure-storage-blob": "azure-ai-projects dependency, not called directly",
    "agent-framework-openai": "Foundry grading, measured by outbound_call",
    "openai": "Foundry grading over httpx, measured by outbound_call",
    "asyncpg": "PostgreSQL connect via outbound_call, statements via "
    "measure_statements",
    "sqlalchemy": "PostgreSQL statements, traced by SQLAlchemyInstrumentor",
    "psycopg2-binary": "Alembic migration job only, not runtime code",
    "azure-monitor-opentelemetry": "telemetry export, not a dependency",
    "azure-monitor-opentelemetry-exporter": "telemetry export, not a dependency",
    "grpcio": "OTLP telemetry export, not a dependency",
    "googleapis-common-protos": "OTLP protobuf definitions",
    "requests": "sync azure-core, msal, and telemetry exporters; never imported "
    "by runtime code",
    "requests-oauthlib": "msrest dependency of the telemetry exporter",
    "urllib3": "requests internals",
    "httptools": "uvicorn inbound HTTP parser",
    "websockets": "uvicorn inbound websocket support",
}

_FORBIDDEN_IMPORTS = (
    "aiohttp",
    "requests",
    "urllib3",
    "urllib.request",
    "http.client",
    "websockets",
    "grpc",
    "psycopg2",
    "psycopg",
)

_CLIENT_CONSTRUCTORS = frozenset(
    {
        "AsyncClient",
        "Client",
        "AsyncHTTPTransport",
        "HTTPTransport",
        "ClientSession",
        "AsyncOpenAI",
        "OpenAI",
        "AsyncAzureOpenAI",
        "AzureOpenAI",
        "FoundryChatClient",
        "create_async_engine",
        "asyncpg.connect",
    }
)

# The only places runtime code may construct a client, transport, or credential.
_FACTORY_SITES = {
    "src/learn_to_cloud/core/http_client.py": {
        "httpx.AsyncClient",
        "httpx.AsyncHTTPTransport",
    },
    "src/learn_to_cloud/core/outbound.py": {
        "httpx.AsyncHTTPTransport",
    },
    "src/learn_to_cloud/core/azure_auth.py": {
        "MeasuredCredential",
        "ManagedIdentityCredential",
    },
    "src/learn_to_cloud/core/database.py": {
        "asyncpg.connect",
        "create_async_engine",
    },
    "src/learn_to_cloud/core/auth.py": {"httpx2.AsyncHTTPTransport"},
    # Migration job only: a separate sync process that exports no telemetry.
    "src/learn_to_cloud/migrations/env.py": {"DefaultAzureCredential"},
    "src/learn_to_cloud/services/verification_grader.py": {
        "DefaultAzureCredential",
        "FoundryChatClient",
        "ManagedIdentityCredential",
        "MeasuredCredential",
    },
}


def _site(path: Path) -> str:
    return str(path.relative_to(_ROOT))


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _constructed_clients(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if name is None:
            continue
        last = name.rsplit(".", 1)[-1]
        if (
            name in _CLIENT_CONSTRUCTORS
            or last in _CLIENT_CONSTRUCTORS
            or last.endswith("Credential")
        ):
            found.add(name)
    return found


def _imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_every_network_package_in_the_lock_has_a_reviewed_coverage_path():
    with (_ROOT / "uv.lock").open("rb") as lock:
        packages = {package["name"] for package in tomllib.load(lock)["package"]}
    network = {
        name
        for name in packages
        if _NETWORK_PACKAGE.search(name) and not name.startswith("opentelemetry-")
    }

    assert network - _NETWORK_PACKAGES.keys() == set(), (
        "New network-capable package: route it through core/outbound.py and "
        "record how it is covered in _NETWORK_PACKAGES"
    )
    assert _NETWORK_PACKAGES.keys() - network == set(), "Remove stale entries"


@pytest.mark.parametrize("path", _RUNTIME_FILES, ids=_site)
def test_runtime_code_does_not_import_unmeasured_clients(path):
    assert [
        name
        for name in _imports(path)
        if any(
            name == root or name.startswith(f"{root}.") for root in _FORBIDDEN_IMPORTS
        )
    ] == []


@pytest.mark.parametrize("path", _RUNTIME_FILES, ids=_site)
def test_clients_are_only_constructed_in_measured_factories(path):
    allowed = _FACTORY_SITES.get(_site(path), set())
    assert _constructed_clients(path) - allowed == set(), (
        "Build outbound clients with build_http_client, MeasuredTransport, "
        "MeasuredCredential, or outbound_call"
    )


def test_factory_allowlist_matches_the_code():
    actual = {
        _site(path): clients
        for path in _RUNTIME_FILES
        if (clients := _constructed_clients(path))
    }
    assert actual == _FACTORY_SITES
