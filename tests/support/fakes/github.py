"""In-memory GitHub for verification tests."""

from typing import Any

from learn_to_cloud.verification.github_api import WorkflowJob


class FakeGitHub:
    """Answer every :class:`GitHub` read from in-memory data.

    ``repos`` maps ``"owner/repo"`` to metadata JSON; a missing key is a 404.
    ``files`` is one repository snapshot; ``tree`` overrides its listing so it
    can name unreadable files. Each ``*_error`` makes that read raise.
    """

    def __init__(
        self,
        *,
        repos: dict[str, dict[str, Any]] | None = None,
        repo_error: Exception | None = None,
        sha: str | None = None,
        sha_error: Exception | None = None,
        run: dict[str, Any] | None = None,
        run_error: Exception | None = None,
        jobs: list[WorkflowJob] | None = None,
        jobs_error: Exception | None = None,
        files: dict[str, str] | None = None,
        tree: list[str] | None = None,
        tree_error: Exception | None = None,
    ) -> None:
        self._repos = dict(repos or {})
        self._repo_error = repo_error
        self._sha = sha
        self._sha_error = sha_error
        self._run = run
        self._run_error = run_error
        self._jobs = list(jobs or [])
        self._jobs_error = jobs_error
        self._files = dict(files or {})
        self._tree = list(tree) if tree is not None else list(self._files)
        self._tree_error = tree_error
        self.file_reads: list[str] = []

    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None:
        if self._repo_error is not None:
            raise self._repo_error
        return self._repos.get(f"{owner}/{repo}")

    async def head_sha(self, owner: str, repo: str, branch: str = "main") -> str | None:
        if self._sha_error is not None:
            raise self._sha_error
        return self._sha

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None:
        if self._run_error is not None:
            raise self._run_error
        return self._run

    async def jobs_for_attempt(
        self, owner: str, repo: str, run_id: int, attempt: int
    ) -> list[WorkflowJob]:
        if self._jobs_error is not None:
            raise self._jobs_error
        return list(self._jobs)

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        if self._tree_error is not None:
            raise self._tree_error
        return list(self._tree)

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None:
        self.file_reads.append(path)
        return self._files.get(path)
