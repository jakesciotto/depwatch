import json
from pathlib import Path

from depwatch import landed
from depwatch.repos import Repos
from tests.conftest import git


def commit_manifest(repo: Path, deps: dict, msg: str, name="package.json") -> str:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(json.dumps({"dependencies": deps}))
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", msg, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


def test_bumps_adds_removes(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    base = commit_manifest(git_repo, {"hono": "4.6.1", "old": "1.0.0"}, "base")
    a = commit_manifest(git_repo, {"hono": "4.7.0", "old": "1.0.0"}, "bump")
    b = commit_manifest(git_repo, {"hono": "4.7.0", "new": "2.0.0"}, "swap")
    out = landed.collect("o/r", git_repo, repos, since=base, until=b)
    rows = [(f.package, f.current, f.target, f.severity, f.commit) for f in out]
    assert rows == [("hono", "4.6.1", "4.7.0", "minor", a), ("new", None, "2.0.0", "minor", b), ("old", "1.0.0", None, "minor", b)]
    assert out[0].raw == "hono 4.6.1 -> 4.7.0 in package.json"
    assert out[1].raw == "new added at 2.0.0 in package.json"
    assert out[2].raw == "old removed (was 1.0.0) in package.json"
    assert out[0].source_url == f"https://github.com/o/r/commit/{a}"
    assert out[0].commit_date
    assert all(f.kind == "landed" for f in out)


def test_dockerfile_base_image_bump(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    (git_repo / "Dockerfile").write_text("FROM node:22-alpine\n")
    git("add", "-A", cwd=git_repo); git("commit", "-q", "-m", "d1", cwd=git_repo)
    base = git("rev-parse", "HEAD", cwd=git_repo)
    (git_repo / "Dockerfile").write_text("FROM node:24-alpine\n")
    git("add", "-A", cwd=git_repo); git("commit", "-q", "-m", "d2", cwd=git_repo)
    head = git("rev-parse", "HEAD", cwd=git_repo)
    out = landed.collect("o/r", git_repo, repos, since=base, until=head)
    assert [(f.package, f.ecosystem, f.current, f.target, f.severity) for f in out] == [("node", "docker", "22-alpine", "24-alpine", "major")]


def test_first_run_emits_nothing(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    head = commit_manifest(git_repo, {"a": "1.0.0"}, "one")
    assert landed.collect("o/r", git_repo, repos, since=None, until=head) == []


def test_no_change_between_heads(tmp_path: Path, git_repo: Path):
    repos = Repos(tmp_path / "data", {})
    head = commit_manifest(git_repo, {"a": "1.0.0"}, "one")
    assert landed.collect("o/r", git_repo, repos, since=head, until=head) == []
