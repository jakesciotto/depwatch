import shutil
import tempfile
from pathlib import Path

from . import manifests
from .models import Dependency, Finding
from .versions import gap


def _index(deps: list[Dependency]) -> dict[tuple[str, str, str], Dependency]:
    return {(d.ecosystem, d.name, d.manifest_path): d for d in deps}


def _parse_at(repos, checkout: Path, sha: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="depwatch-"))
    try:
        return _index(manifests.parse(repos.checkout_tree(checkout, sha, tmp)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def collect(repo: str, checkout: Path, repos, since: str | None, until: str) -> list[Finding]:
    if since is None or since == until:
        return []
    out: list[Finding] = []
    for c in repos.changed_files(checkout, since, until, manifests.MANIFEST_GLOBS):
        before = _parse_at(repos, checkout, f"{c.sha}^")
        after = _parse_at(repos, checkout, c.sha)
        url = f"https://github.com/{repo}/commit/{c.sha}"
        for key in sorted(set(before) | set(after)):
            eco, name, path = key
            old, new = before.get(key), after.get(key)
            if old and new and old.version == new.version:
                continue
            if old and new:
                severity = gap(old.version, new.version) or "patch"
                raw = f"{name} {old.version} -> {new.version} in {path}"
                cur, tgt = old.version, new.version
            elif new:
                severity, raw, cur, tgt = "minor", f"{name} added at {new.version} in {path}", None, new.version
            else:
                severity, raw, cur, tgt = "minor", f"{name} removed (was {old.version}) in {path}", old.version, None
            out.append(Finding(kind="landed", repo=repo, package=name, ecosystem=eco, current=cur, target=tgt,
                               severity=severity, source_url=url, raw=raw, commit=c.sha, commit_date=c.date))
    return out
