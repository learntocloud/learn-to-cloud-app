"""Profile API startup to identify bottlenecks. Run from api/ directory."""

import time

t0 = time.perf_counter()

print("--- IMPORT TIMING ---", flush=True)

t = time.perf_counter()
import asyncio

print(f"stdlib imports: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(f"fastapi: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(f"slowapi: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
from core.config import get_settings

print(f"core.config: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
import logging

from core.logger import configure_logging

print(f"core.logger: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
from core.auth import init_oauth

print(f"core.auth: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
from core.database import (
    create_engine,
    create_session_maker,
    dispose_engine,
    init_db,
)

print(f"core.database (sqlalchemy): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(f"core.telemetry: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(f"core.ratelimit: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(f"core.llm_client: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(f"routes (all routers): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()

print(
    f"services.github_hands_on_verification: {(time.perf_counter()-t)*1000:.0f}ms",
    flush=True,
)

total_imports = time.perf_counter() - t0
print(f"\n=> TOTAL import time: {total_imports*1000:.0f}ms\n", flush=True)

# ------------------------------------------------------------------

print("--- TOP-LEVEL CODE ---", flush=True)

t = time.perf_counter()
configure_logging()
print(f"configure_logging(): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
logger = logging.getLogger(__name__)
print(f"getLogger(): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
settings = get_settings()
print(f"get_settings(): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

# ------------------------------------------------------------------

print("\n--- LIFESPAN STEPS ---", flush=True)

t = time.perf_counter()
init_oauth()
print(f"init_oauth(): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
engine = create_engine()
print(f"create_engine(): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)

t = time.perf_counter()
sm = create_session_maker(engine)
print(f"create_session_maker(): {(time.perf_counter()-t)*1000:.0f}ms", flush=True)


async def measure_init_db():
    t = time.perf_counter()
    await init_db(engine)
    print(f"init_db() [SELECT 1]: {(time.perf_counter()-t)*1000:.0f}ms", flush=True)
    await dispose_engine(engine)


asyncio.run(measure_init_db())

total = time.perf_counter() - t0
print(f"\n{'='*50}", flush=True)
print(f"TOTAL startup time: {total*1000:.0f}ms", flush=True)
print(f"  - imports: {total_imports*1000:.0f}ms", flush=True)
print(f"  - runtime: {(total - total_imports)*1000:.0f}ms", flush=True)
