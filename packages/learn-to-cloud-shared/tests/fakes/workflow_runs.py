"""In-memory workflow runs for verification tests."""

from typing import Any


class InMemoryWorkflowRuns:
    """Return a configured run or raise the supplied exception."""

    def __init__(
        self,
        run: dict[str, Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._run = run
        self._error = error

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None:
        if self._error is not None:
            raise self._error
        return self._run
