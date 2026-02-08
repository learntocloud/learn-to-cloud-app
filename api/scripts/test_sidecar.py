"""Test script to reproduce copilot CLI Azure BYOK hang in headless mode.

Usage:
    cd api
    uv run python scripts/test_sidecar.py

Requires:
    - LLM_CLI_URL=http://localhost:4321 (Docker sidecar running)
    - LLM_BASE_URL, LLM_API_KEY, LLM_MODEL set in .env
"""

import asyncio
import os
import time

# Load .env
from dotenv import load_dotenv

load_dotenv()

# Override to use HTTP sidecar mode (not stdio)
os.environ.pop("LLM_CLI_PATH", None)
os.environ["LLM_CLI_URL"] = "http://localhost:4321"


async def test_sidecar():
    from copilot import CopilotClient
    from copilot.types import CopilotClientOptions, SessionConfig

    print(f"LLM_CLI_URL: {os.environ.get('LLM_CLI_URL')}")
    print(f"LLM_BASE_URL: {os.environ.get('LLM_BASE_URL')}")
    print(f"LLM_MODEL: {os.environ.get('LLM_MODEL')}")
    print(f"LLM_PROVIDER_TYPE: {os.environ.get('LLM_PROVIDER_TYPE', 'azure')}")
    print()

    # Connect to sidecar
    options = CopilotClientOptions(
        cli_url=os.environ["LLM_CLI_URL"],
        auto_start=False,
    )
    client = CopilotClient(options)
    await client.start()
    print("[OK] Connected to CLI sidecar")

    # Build BYOK provider
    provider = {
        "type": os.environ.get("LLM_PROVIDER_TYPE", "azure"),
        "base_url": os.environ["LLM_BASE_URL"],
        "api_key": os.environ["LLM_API_KEY"],
        "wire_api": os.environ.get("LLM_WIRE_API", "completions"),
    }
    if provider["type"] == "azure":
        provider["azure"] = {
            "api_version": os.environ.get("LLM_API_VERSION", "2024-10-21")
        }

    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    config = SessionConfig(model=model, provider=provider)

    print(f"[..] Creating session (model={model}, provider.type={provider['type']})")
    session = await client.create_session(config)
    print("[OK] Session created")

    # Collect response
    response_content = ""
    done = asyncio.Event()
    events_received = []

    def on_event(event):
        nonlocal response_content
        event_type = (
            event.type.value if hasattr(event.type, "value") else str(event.type)
        )
        events_received.append(event_type)
        print(f"  [EVENT] {event_type}")
        if event_type == "assistant.message":
            response_content = event.data.content
        elif event_type == "session.idle":
            done.set()

    session.on(on_event)

    print("[..] Sending prompt: 'What is 2+2? Answer with just the number.'")
    start = time.perf_counter()
    await session.send({"prompt": "What is 2+2? Answer with just the number."})

    # Wait with timeout
    timeout = 30
    print(f"[..] Waiting for response (timeout={timeout}s)...")
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
        elapsed = time.perf_counter() - start
        print(f"[OK] Response received in {elapsed:.1f}s: {response_content!r}")
        print(f"     Events: {events_received}")
    except TimeoutError:
        elapsed = time.perf_counter() - start
        print(f"[FAIL] TIMED OUT after {elapsed:.1f}s")
        print(f"       Events received: {events_received}")
        print(f"       Response so far: {response_content!r}")
        print()
        print("  >>> BUG CONFIRMED: Azure BYOK hangs in headless mode <<<")

    await session.destroy()
    await client.stop()


if __name__ == "__main__":
    asyncio.run(test_sidecar())
