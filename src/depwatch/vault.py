from typing import Callable

from .repos import RepoError, Repos


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, repos: Repos, repo: str, folder: str, committer_name: str = "depwatch",
                 committer_email: str = "depwatch@localhost"):
        self.repos, self.repo, self.folder = repos, repo, folder.strip("/")
        self.committer_name, self.committer_email = committer_name, committer_email

    def publish(self, rel_path: str, build: Callable[[str | None], str], message: str, attempts: int = 3) -> None:
        if not rel_path.startswith(self.folder + "/"):
            raise VaultError(f"{rel_path} is outside {self.folder}")
        last = ""
        for _ in range(attempts):
            path = self.repos.sync(self.repo)
            target = path / rel_path
            existing = target.read_text() if target.exists() else None
            content = build(existing)
            if content == existing:
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self.repos._git("add", "--", self.folder, cwd=path)
            self.repos._git(
                "-c", f"user.name={self.committer_name}", "-c", f"user.email={self.committer_email}",
                "-c", "commit.gpgsign=false", "commit", "-q", "-m", message, cwd=path,
            )
            try:
                self.repos._git("push", "-q", "origin", f"HEAD:{self.repos.default_branch(path)}", cwd=path)
                return
            except RepoError as e:
                last = str(e)
        raise VaultError(f"push rejected after {attempts} attempts: {last}")
