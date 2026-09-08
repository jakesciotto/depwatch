import fnmatch
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .manifests import MANIFEST_GLOBS


class RepoError(Exception):
    pass


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str
    files: list[str]


class Repos:
    def __init__(self, data_dir: Path, git_env: dict[str, str], remote_base: str = "https://github.com/"):
        self.root = data_dir / "repos"
        self.env = {**os.environ, **git_env}
        self.remote_base = remote_base

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True)
        if r.returncode != 0:
            err = r.stderr.replace(self.env.get("GITHUB_TOKEN", "\0"), "***")
            raise RepoError(f"git {args[0]} failed: {err.strip()}")
        return r.stdout

    def sync(self, repo: str) -> Path:
        path = self.root / repo.split("/")[-1]
        if not (path / ".git").exists():
            self.root.mkdir(parents=True, exist_ok=True)
            self._git("clone", "-q", "--filter=blob:none", "--single-branch",
                      f"{self.remote_base}{repo}.git", str(path))
            self._git("remote", "set-head", "origin", "-a", cwd=path)
        else:
            self._git("fetch", "-q", "--prune", "origin", cwd=path)
            self._git("remote", "set-head", "origin", "-a", cwd=path)
            self._git("reset", "-q", "--hard", f"origin/{self.default_branch(path)}", cwd=path)
        return path

    def default_branch(self, path: Path) -> str:
        ref = self._git("symbolic-ref", "refs/remotes/origin/HEAD", cwd=path).strip()
        return ref.rsplit("/", 1)[-1]

    def head(self, path: Path) -> str:
        return self._git("rev-parse", "HEAD", cwd=path).strip()

    def changed_files(self, path: Path, since: str | None, until: str, globs: tuple[str, ...]) -> list[Commit]:
        rng = f"{since}..{until}" if since else until
        extra = [] if since else ["-n", "50"]
        out = self._git("log", "--reverse", "--name-only", "--format=%x1e%H %cI", *extra, rng, cwd=path)
        commits: list[Commit] = []
        for block in out.split("\x1e")[1:]:
            header, _, body = block.partition("\n")
            sha, date = header.split()
            files = [f for f in body.splitlines() if f and any(fnmatch.fnmatch(Path(f).name, g) for g in globs)]
            if files:
                commits.append(Commit(sha, date, files))
        return commits

    def show(self, path: Path, sha: str, file: str) -> str | None:
        r = subprocess.run(["git", "show", f"{sha}:{file}"], cwd=path, env=self.env, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def checkout_tree(self, path: Path, sha: str, dest: Path) -> Path:
        listing = self._git("ls-tree", "-r", "--name-only", sha, cwd=path).splitlines()
        dest.mkdir(parents=True, exist_ok=True)
        for f in listing:
            if "node_modules" in f or not any(fnmatch.fnmatch(Path(f).name, g) for g in MANIFEST_GLOBS):
                continue
            content = self.show(path, sha, f)
            if content is None:
                continue
            target = dest / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        return dest
