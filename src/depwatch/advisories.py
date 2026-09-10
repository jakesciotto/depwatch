from pathlib import Path

from . import manifests
from .models import Dependency, Finding

_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
RAW_CAP = 4000


def _query_set(checkout: Path) -> list[Dependency]:
    """Direct dependencies first, then everything the lockfiles pin, one entry per version."""
    seen: set[tuple[str, str, str]] = set()
    out: list[Dependency] = []
    for d in manifests.parse(checkout) + manifests.locked(checkout):
        key = (d.ecosystem, d.name, d.version)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def collect(repo: str, checkout: Path, github, osv, state) -> list[Finding]:
    alerts = list(github.open_alerts(repo))
    if osv is not None:
        alerts += osv.alerts(_query_set(checkout))
    out: list[Finding] = []
    seen_permalinks: set[str] = set()
    for a in alerts:
        if a.permalink in seen_permalinks:
            continue
        seen_permalinks.add(a.permalink)
        if state.advisory_seen(repo, a.permalink):
            continue
        out.append(Finding(kind="advisory", repo=repo, package=a.package, ecosystem=a.ecosystem,
                           current=a.vulnerable_range, target=a.first_patched, severity=a.severity,
                           source_url=a.permalink, raw=f"{a.summary}\n\n{a.description}".strip()[:RAW_CAP],
                           commit_date=a.created_at))
    out.sort(key=lambda f: (_ORDER.get(f.severity, 9), f.package))
    return out
