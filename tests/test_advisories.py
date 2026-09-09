from pathlib import Path

from depwatch import advisories
from depwatch.github import Alert
from depwatch.state import State


def alert(ghsa, sev, pkg="hono", eco="npm", patched="4.6.2", manifest_path="package.json"):
    return Alert(ghsa_id=ghsa, severity=sev, package=pkg, ecosystem=eco, vulnerable_range="< 4.6.2",
                 first_patched=patched, summary="Summary", description="Desc", permalink=f"https://github.com/advisories/{ghsa}",
                 manifest_path=manifest_path, created_at="2026-09-01T00:00:00Z")


class FakeGitHub:
    def __init__(self, alerts): self.alerts = alerts
    def open_alerts(self, repo): return self.alerts


def test_collect_orders_by_severity_and_drops_seen(tmp_path: Path):
    gh = FakeGitHub([alert("GHSA-1", "moderate", pkg="b"), alert("GHSA-2", "critical"), alert("GHSA-3", "high", pkg="a"), alert("GHSA-4", "high", pkg="z")])
    st = State(tmp_path / "db")
    out = advisories.collect("o/r", gh, st)
    assert [(f.severity, f.package) for f in out] == [("critical", "hono"), ("high", "a"), ("high", "z"), ("moderate", "b")]
    f = out[0]
    assert (f.kind, f.current, f.target, f.source_url) == ("advisory", "< 4.6.2", "4.6.2", "https://github.com/advisories/GHSA-2")
    assert f.raw == "Summary\n\nDesc" and f.commit_date == "2026-09-01T00:00:00Z"
    st.mark_advisories(out[:1])
    assert [f.source_url for f in advisories.collect("o/r", gh, st)] == [
        "https://github.com/advisories/GHSA-3", "https://github.com/advisories/GHSA-4", "https://github.com/advisories/GHSA-1"]


def test_collect_dedupes_same_permalink_across_manifests(tmp_path: Path):
    gh = FakeGitHub([
        alert("GHSA-5", "high", manifest_path="server/package.json"),
        alert("GHSA-5", "high", manifest_path="web/package.json"),
    ])
    st = State(tmp_path / "db")
    out = advisories.collect("o/r", gh, st)
    assert len(out) == 1
    assert out[0].source_url == "https://github.com/advisories/GHSA-5"
