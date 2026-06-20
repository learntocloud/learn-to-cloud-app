"""Tests for repo_utils shared utilities.

Tests cover:
- GitHub URL parsing and validation (extract_repo_info)
- Repository identity resolution (resolve_repository / RepositoryRef)
"""

import pytest

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.repo_utils import (
    RepositoryRef,
    extract_repo_info,
    resolve_repository,
)

# ---------------------------------------------------------------------------
# extract_repo_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractRepoInfo:
    """Tests for GitHub URL parsing."""

    def test_standard_url(self):
        owner, repo = extract_repo_info("https://github.com/testuser/journal-starter")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_trailing_slash(self):
        owner, repo = extract_repo_info("https://github.com/testuser/journal-starter/")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_git_suffix(self):
        owner, repo = extract_repo_info(
            "https://github.com/testuser/journal-starter.git"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_subpath(self):
        owner, repo = extract_repo_info(
            "https://github.com/testuser/journal-starter/tree/main/infra"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_whitespace(self):
        owner, repo = extract_repo_info(
            "  https://github.com/testuser/journal-starter  "
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            extract_repo_info("https://gitlab.com/testuser/repo")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            extract_repo_info("")

    def test_non_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            extract_repo_info("not-a-url")

    def test_www_github_url(self):
        owner, repo = extract_repo_info("https://www.github.com/testuser/my-repo")
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_http_url(self):
        owner, repo = extract_repo_info("http://github.com/testuser/my-repo")
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_query_string_stripped(self):
        owner, repo = extract_repo_info(
            "https://github.com/testuser/my-repo?tab=readme"
        )
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_fragment_stripped(self):
        owner, repo = extract_repo_info("https://github.com/testuser/my-repo#readme")
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_bare_github_url_without_scheme(self):
        owner, repo = extract_repo_info("github.com/testuser/my-repo")
        assert owner == "testuser"
        assert repo == "my-repo"


# ---------------------------------------------------------------------------
# resolve_repository / RepositoryRef
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveRepository:
    """Tests for parsing repo identity from a validated submission URL.

    ``resolve_repository`` intentionally does not re-check ownership or fork
    name: the submission value is server-derived and DB-validated upstream.
    """

    def test_parses_owner_and_repo(self):
        result = resolve_repository("https://github.com/testuser/journal-starter")
        assert result == RepositoryRef(owner="testuser", repo="journal-starter")

    def test_preserves_owner_casing(self):
        result = resolve_repository("https://github.com/TestUser/journal-starter")
        assert result == RepositoryRef(owner="TestUser", repo="journal-starter")

    def test_strips_git_suffix_and_subpath(self):
        result = resolve_repository(
            "https://github.com/testuser/journal-starter.git/tree/main"
        )
        assert result == RepositoryRef(owner="testuser", repo="journal-starter")

    def test_malformed_url_returns_validation_result(self):
        result = resolve_repository("not-a-url")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert "Invalid GitHub repository URL" in result.message

    def test_non_github_host_returns_validation_result(self):
        result = resolve_repository("https://gitlab.com/testuser/repo")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False


@pytest.mark.unit
class TestRepositoryRefPayload:
    """RepositoryRef survives a Durable payload round trip."""

    def test_round_trip(self):
        ref = RepositoryRef(owner="testuser", repo="journal-starter")
        assert RepositoryRef.from_payload(ref.to_payload()) == ref

    def test_from_payload_rejects_non_string_fields(self):
        with pytest.raises(TypeError):
            RepositoryRef.from_payload({"owner": "testuser", "repo": 5})
