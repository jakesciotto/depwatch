import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """An initialised repo on branch main with one empty commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    return repo


@pytest.fixture
def bare_remote(tmp_path: Path, git_repo: Path) -> Path:
    """A bare remote that git_repo pushes main to, wired as origin."""
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("remote", "add", "origin", str(remote), cwd=git_repo)
    git("push", "-q", "-u", "origin", "main", cwd=git_repo)
    return remote
