"""Repository target value-object contracts."""

from dataclasses import FrozenInstanceError

import pytest

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget


@pytest.mark.parametrize("repo", ["project", "learner"])
def test_repository_location(repo):
    target = GitHubRepositoryTarget(owner="learner", repo=repo)

    assert target.full_name == f"learner/{repo}"
    assert target.url == f"https://github.com/learner/{repo}"
    assert target.forked_from is None


def test_repository_name_is_required():
    with pytest.raises(TypeError, match="repo"):
        GitHubRepositoryTarget(owner="learner")


def test_repository_target_is_immutable():
    target = GitHubRepositoryTarget("learner", "project", "upstream/project")

    assert target.forked_from == "upstream/project"
    with pytest.raises(FrozenInstanceError):
        target.repo = "other"
