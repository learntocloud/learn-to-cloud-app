"""In-memory branch references for verification tests."""


class InMemoryRepoRef:
    """Return a configured SHA or raise the supplied exception."""

    def __init__(
        self,
        sha: str | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._sha = sha
        self._error = error

    async def head_sha(self, owner: str, repo: str, branch: str = "main") -> str | None:
        if self._error is not None:
            raise self._error
        return self._sha
