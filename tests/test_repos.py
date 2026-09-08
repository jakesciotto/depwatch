from pathlib import Path

import pytest

from depwatch.manifests import MANIFEST_GLOBS
from depwatch.repos import RepoError, Repos
from tests.conftest import git


def commit_file(repo: Path, name: str, text: str, msg: str) -> str:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text)
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", msg, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


def test_sync_clones_then_fetches(tmp_path: Path, git_repo: Path, bare_remote: Path):
    repos = Repos(tmp_path / "data", {}, remote_base=str(tmp_path) + "/")
    sha1 = commit_file(git_repo, "package.json", "{}", "one")
    git("push", "-q", cwd=git_repo)
    path = repos.sync("remote")
    assert path == tmp_path / "data/repos/remote"
    assert repos.head(path) == sha1
    sha2 = commit_file(git_repo, "package.json", '{"a":1}', "two")
    git("push", "-q", cwd=git_repo)
    assert repos.head(repos.sync("remote")) == sha2


def test_sync_failure_raises_repo_error(tmp_path: Path):
    repos = Repos(tmp_path / "data", {}, remote_base=str(tmp_path) + "/")
    with pytest.raises(RepoError):
        repos.sync("does-not-exist")


def test_changed_files_between_heads(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    base = git("rev-parse", "HEAD", cwd=git_repo)
    a = commit_file(git_repo, "package.json", "{}", "add manifest")
    commit_file(git_repo, "src/x.ts", "1", "code only")
    b = commit_file(git_repo, "server/Dockerfile", "FROM node:22", "docker")
    commits = repos.changed_files(git_repo, base, b, MANIFEST_GLOBS)
    assert [(c.sha, c.files) for c in commits] == [(a, ["package.json"]), (b, ["server/Dockerfile"])]
    assert commits[0].date[:2] == "20"


def test_changed_files_without_since_uses_recent_history(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    a = commit_file(git_repo, "pyproject.toml", "[project]", "py")
    assert [c.sha for c in repos.changed_files(git_repo, None, a, MANIFEST_GLOBS)] == [a]


def test_show_and_checkout_tree(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    a = commit_file(git_repo, "package.json", '{"v":1}', "one")
    commit_file(git_repo, "notes.md", "x", "noise")
    b = commit_file(git_repo, "package.json", '{"v":2}', "two")
    assert repos.show(git_repo, a, "package.json") == '{"v":1}'
    assert repos.show(git_repo, a, "missing.json") is None
    dest = repos.checkout_tree(git_repo, a, tmp_path / "tree")
    assert (dest / "package.json").read_text() == '{"v":1}'
    assert not (dest / "notes.md").exists()
    assert (repos.checkout_tree(git_repo, b, tmp_path / "tree2") / "package.json").read_text() == '{"v":2}'
