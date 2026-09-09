from .models import Finding

_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
RAW_CAP = 4000


def collect(repo: str, github, state) -> list[Finding]:
    out: list[Finding] = []
    seen_permalinks: set[str] = set()
    for a in github.open_alerts(repo):
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
