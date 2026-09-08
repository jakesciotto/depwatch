import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Finding

SCHEMA = """
create table if not exists repo_heads (repo text primary key, head text not null);
create table if not exists seen_releases (
  repo text, package text, ecosystem text, target text,
  primary key (repo, package, ecosystem, target));
create table if not exists seen_advisories (repo text, source_url text, primary key (repo, source_url));
create table if not exists runs (
  id integer primary key, kind text, status text, note_path text, findings integer, finished_at text);
"""


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, isolation_level="DEFERRED")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def head(self, repo: str) -> str | None:
        row = self.conn.execute("select head from repo_heads where repo = ?", (repo,)).fetchone()
        return row[0] if row else None

    def set_head(self, repo: str, sha: str) -> None:
        self.conn.execute("insert or replace into repo_heads (repo, head) values (?, ?)", (repo, sha))

    def release_seen(self, repo: str, package: str, ecosystem: str, target: str | None) -> bool:
        row = self.conn.execute(
            "select 1 from seen_releases where repo=? and package=? and ecosystem=? and target=?",
            (repo, package, ecosystem, target),
        ).fetchone()
        return row is not None

    def mark_releases(self, findings: Iterable[Finding]) -> None:
        self.conn.executemany(
            "insert or ignore into seen_releases values (?, ?, ?, ?)",
            [(f.repo, f.package, f.ecosystem, f.target) for f in findings if f.kind == "release"],
        )

    def advisory_seen(self, repo: str, source_url: str) -> bool:
        row = self.conn.execute(
            "select 1 from seen_advisories where repo=? and source_url=?", (repo, source_url)
        ).fetchone()
        return row is not None

    def mark_advisories(self, findings: Iterable[Finding]) -> None:
        self.conn.executemany(
            "insert or ignore into seen_advisories values (?, ?)",
            [(f.repo, f.source_url) for f in findings if f.kind == "advisory"],
        )

    def record_run(self, kind: str, status: str, note_path: str | None, findings: int) -> None:
        self.conn.execute(
            "insert into runs (kind, status, note_path, findings, finished_at) values (?, ?, ?, ?, ?)",
            (kind, status, note_path, findings, datetime.now(timezone.utc).isoformat()),
        )

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.rollback()
        self.conn.close()
