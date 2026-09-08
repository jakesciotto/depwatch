from pathlib import Path

import pytest

from depwatch.repos import Repos
from depwatch.vault import Vault, VaultError
from tests.conftest import git


def make(tmp_path: Path, bare_remote: Path):
    repos = Repos(tmp_path / "data", {}, remote_base=str(tmp_path) + "/")
    return Vault(repos, "remote", "resources/dependencies", {}), repos


def test_publish_creates_and_pushes(tmp_path: Path, git_repo: Path, bare_remote: Path):
    vault, _ = make(tmp_path, bare_remote)
    vault.publish("resources/dependencies/2026-W37.md", lambda existing: "hello\n", "depwatch: 2026-W37 digest")
    git("pull", "-q", cwd=git_repo)
    assert (git_repo / "resources/dependencies/2026-W37.md").read_text() == "hello\n"
    assert git("log", "-1", "--format=%an %s", cwd=git_repo) == "depwatch depwatch: 2026-W37 digest"


def test_publish_appends_on_existing(tmp_path: Path, git_repo: Path, bare_remote: Path):
    vault, _ = make(tmp_path, bare_remote)
    vault.publish("resources/dependencies/w.md", lambda e: "a\n", "one")
    vault.publish("resources/dependencies/w.md", lambda e: (e or "") + "b\n", "two")
    git("pull", "-q", cwd=git_repo)
    assert (git_repo / "resources/dependencies/w.md").read_text() == "a\nb\n"


def test_publish_retries_after_rejected_push(tmp_path: Path, git_repo: Path, bare_remote: Path):
    vault, repos = make(tmp_path, bare_remote)
    vault.publish("resources/dependencies/w.md", lambda e: "a\n", "one")
    git("pull", "-q", cwd=git_repo)  # bring git_repo up to date before it races the second push
    pushed = []
    original = repos._git
    def racing_git(*args, cwd=None):
        if args[0] == "push" and not pushed:
            pushed.append(1)
            (git_repo / "other.md").write_text("x")
            git("add", "-A", cwd=git_repo); git("commit", "-q", "-m", "race", cwd=git_repo); git("push", "-q", cwd=git_repo)
        return original(*args, cwd=cwd)
    repos._git = racing_git
    vault.publish("resources/dependencies/w.md", lambda e: (e or "") + "b\n", "two")
    git("pull", "-q", cwd=git_repo)
    assert (git_repo / "resources/dependencies/w.md").read_text() == "a\nb\n"
    assert (git_repo / "other.md").exists()


def test_publish_gives_up_after_attempts(tmp_path: Path, git_repo: Path, bare_remote: Path):
    vault, repos = make(tmp_path, bare_remote)
    original = repos._git
    counter = [0]
    def always_race(*args, cwd=None):
        if args[0] == "push":
            counter[0] += 1
            # a distinct file each time: len(iterdir()) does not change race to race
            (git_repo / "n.md").write_text(str(counter[0]))
            git("add", "-A", cwd=git_repo); git("commit", "-q", "-m", "race", cwd=git_repo); git("push", "-q", cwd=git_repo)
        return original(*args, cwd=cwd)
    repos._git = always_race
    with pytest.raises(VaultError, match="3 attempts"):
        vault.publish("resources/dependencies/w.md", lambda e: "a\n", "one", attempts=3)


def test_unchanged_content_skips_commit(tmp_path: Path, git_repo: Path, bare_remote: Path):
    vault, _ = make(tmp_path, bare_remote)
    vault.publish("resources/dependencies/w.md", lambda e: "a\n", "one")
    vault.publish("resources/dependencies/w.md", lambda e: e, "two")
    git("pull", "-q", cwd=git_repo)
    assert git("log", "-1", "--format=%s", cwd=git_repo) == "one"


def test_path_outside_folder_is_refused(tmp_path: Path, git_repo: Path, bare_remote: Path):
    vault, _ = make(tmp_path, bare_remote)
    with pytest.raises(VaultError, match="outside"):
        vault.publish("areas/work/x.md", lambda e: "a\n", "one")
