"""Every network-capable package in uv.lock must have a reviewed tracing path.

A library switch (such as authlib moving from httpx to httpx2) can silently
produce untraced calls, so new network packages fail until they are reviewed.
"""

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_NETWORK_PACKAGE = re.compile(
    r"http|request|url|aio|grpc|socket|websocket|pg|psycopg|sql|redis|mongo"
    r"|openai|anthropic|boto|kafka|amqp|mqtt|ftp|smtp|ldap|azure|google|client|sdk"
)

# Every locked package that can open network connections, and how it is covered.
_NETWORK_PACKAGES = {
    "httpx": "openai transport only, traced by HTTPXClientInstrumentor",
    "httpcore": "httpx internals",
    "httpx2": "GitHub, OAuth, and deployed APIs, traced by HTTPX2ClientInstrumentor",
    "httpcore2": "httpx2 internals",
    "httpx2-jsfetch": "httpx2 browser backend, unused on CPython",
    "aiohttp": "azure-core async transport for Entra tokens",
    "aiohappyeyeballs": "aiohttp internals",
    "aiosignal": "aiohttp internals",
    "azure-core": "azure SDK pipeline, traced by azure-core-tracing-opentelemetry",
    "azure-core-tracing-opentelemetry": "azure SDK tracing plugin",
    "azure-identity": "Entra credentials, traced by azure-core",
    "azure-ai-inference": "agent-framework-foundry dependency, not called directly",
    "azure-ai-projects": "agent-framework-foundry dependency, not called directly",
    "azure-storage-blob": "azure-ai-projects dependency, not called directly",
    "agent-framework-openai": "Foundry grading over openai",
    "openai": "Foundry grading over httpx",
    "asyncpg": "PostgreSQL driver under SQLAlchemy",
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
}


def test_every_network_package_in_the_lock_has_a_reviewed_coverage_path():
    with (_ROOT / "uv.lock").open("rb") as lock:
        packages = {package["name"] for package in tomllib.load(lock)["package"]}
    network = {
        name
        for name in packages
        if _NETWORK_PACKAGE.search(name) and not name.startswith("opentelemetry-")
    }

    assert network - _NETWORK_PACKAGES.keys() == set(), (
        "New network-capable package: confirm its calls are traced and record "
        "how in _NETWORK_PACKAGES"
    )
    assert _NETWORK_PACKAGES.keys() - network == set(), "Remove stale entries"
