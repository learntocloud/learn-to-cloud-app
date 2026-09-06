"""In-memory repository files for verification tests."""


class InMemoryRepoFiles:
    """One repository snapshot, accepting identity and branch for compatibility.

    An explicit tree can include unreadable files. ``tree_error`` makes discovery
    raise the supplied exception.
    """

    def __init__(
        self,
        files: dict[str, str] | None = None,
        *,
        tree: list[str] | None = None,
        tree_error: Exception | None = None,
    ) -> None:
        self._files = dict(files or {})
        self._tree = list(tree) if tree is not None else list(self._files)
        self._tree_error = tree_error

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        if self._tree_error is not None:
            raise self._tree_error
        return list(self._tree)

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None:
        return self._files.get(path)
