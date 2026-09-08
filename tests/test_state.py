from pathlib import Path

from depwatch.models import Finding
from depwatch.state import State


def rel(repo="o/r", pkg="p", target="2.0.0") -> Finding:
    return Finding(kind="release", repo=repo, package=pkg, ecosystem="npm", current="1.0.0",
                   target=target, severity="major", source_url="u", raw="")


def adv(repo="o/r", url="https://github.com/advisories/GHSA-1") -> Finding:
    return Finding(kind="advisory", repo=repo, package="p", ecosystem="npm", current="1.0.0",
                   target="1.0.1", severity="high", source_url=url, raw="")


def test_heads_roundtrip(tmp_path: Path):
    s = State(tmp_path / "db")
    assert s.head("o/r") is None
    s.set_head("o/r", "abc")
    s.commit()
    assert State(tmp_path / "db").head("o/r") == "abc"


def test_release_seen_after_mark(tmp_path: Path):
    s = State(tmp_path / "db")
    f = rel()
    assert not s.release_seen(f.repo, f.package, f.ecosystem, f.target)
    s.mark_releases([f])
    assert s.release_seen(f.repo, f.package, f.ecosystem, f.target)
    assert not s.release_seen(f.repo, f.package, f.ecosystem, "3.0.0")


def test_advisory_seen_after_mark(tmp_path: Path):
    s = State(tmp_path / "db")
    f = adv()
    assert not s.advisory_seen(f.repo, f.source_url)
    s.mark_advisories([f])
    assert s.advisory_seen(f.repo, f.source_url)


def test_uncommitted_marks_do_not_persist(tmp_path: Path):
    s = State(tmp_path / "db")
    s.mark_releases([rel()])
    s.close()
    assert not State(tmp_path / "db").release_seen("o/r", "p", "npm", "2.0.0")


def test_record_run(tmp_path: Path):
    s = State(tmp_path / "db")
    s.record_run("digest", "ok", "resources/dependencies/2026-W37.md", 3)
    s.commit()
    rows = s.conn.execute("select kind, status, note_path, findings from runs").fetchall()
    assert rows == [("digest", "ok", "resources/dependencies/2026-W37.md", 3)]
