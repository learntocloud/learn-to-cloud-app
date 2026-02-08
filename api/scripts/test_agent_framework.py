"""Test Agent Framework with Azure OpenAI + function tools.

Usage:
    cd api
    uv run python scripts/test_agent_framework.py
"""

import asyncio
import os
import time
from typing import Annotated

import httpx
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()


async def fetch_github_file(
    path: Annotated[str, Field(description="File path within the repository")],
    branch: Annotated[str, Field(description="Branch name")] = "main",
) -> str:
    """Fetch file contents from the learner's repository."""
    owner = "madebygps"
    repo = "journal-starter"
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.text[:5000]
        return f'<file_content path="{path}">\n{content}\n</file_content>'


async def main():
    from agent_framework.azure import AzureOpenAIChatClient

    endpoint = os.environ["LLM_BASE_URL"]
    api_key = os.environ["LLM_API_KEY"]
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    print(f"Endpoint: {endpoint}")
    print(f"Model: {model}")
    print()

    client = AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=model,
        api_key=api_key,
    )

    agent = client.create_agent(
        instructions=(
            "You are a code reviewer. Review the file and say if "
            "logging is configured. Respond with JSON: "
            '{"tasks": [{"task_id": "logging-setup", '
            '"passed": true/false, "feedback": "..."}]}'
        ),
        tools=[fetch_github_file],
    )

    print("[..] Running agent with tool call...")
    start = time.perf_counter()
    result = await agent.run("Fetch api/main.py and check if logging is configured.")
    elapsed = time.perf_counter() - start

    print(f"[OK] Response in {elapsed:.1f}s:")
    print(result.text[:500])


if __name__ == "__main__":
    asyncio.run(main())
