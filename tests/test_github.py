import json
import os
import subprocess
from pathlib import Path

import httpx

from depwatch.github import Alert, GitHub


TOKEN = "shhh-secret"


def make(handler, tmp_path: Path):
    return GitHub(httpx.Client(transport=httpx.MockTransport(handler)), token=TOKEN, data_dir=tmp_path)


def test_release_notes_in_range(fixtures: Path, tmp_path: Path):
    body = json.loads((fixtures / "github/releases.json").read_text())
    seen = []
    def handler(req):
        seen.append((req.url.path, req.headers.get("authorization")))
        return httpx.Response(200, json=body)
    gh = make(handler, tmp_path)
    notes, url = gh.release_notes("honojs/hono", after="4.6.1", upto="4.7.0")
    assert notes == "### v4.7.0\n## 4.7.0\nNew router.\n\n### v4.6.5\nFix."
    assert url == "https://github.com/honojs/hono/releases/tag/v4.7.0"
    assert seen == [("/repos/honojs/hono/releases", f"Bearer {TOKEN}")]


def test_release_notes_none_in_range(fixtures: Path, tmp_path: Path):
    body = json.loads((fixtures / "github/releases.json").read_text())
    gh = make(lambda req: httpx.Response(200, json=body), tmp_path)
    notes, url = gh.release_notes("honojs/hono", after="4.7.0", upto="4.8.0")
    assert notes == ""
    assert url == "https://github.com/honojs/hono/releases"


def test_release_notes_cap(tmp_path: Path):
    body = [{"tag_name": "v2.0.0", "html_url": "u", "body": "x" * 10000}]
    gh = make(lambda req: httpx.Response(200, json=body), tmp_path)
    notes, _ = gh.release_notes("o/r", after="1.0.0", upto="2.0.0")
    assert len(notes) == 4000


def test_release_notes_api_error_is_empty(tmp_path: Path):
    gh = make(lambda req: httpx.Response(500), tmp_path)
    assert gh.release_notes("o/r", "1", "2") == ("", "https://github.com/o/r/releases")


def test_open_alerts(fixtures: Path, tmp_path: Path):
    body = json.loads((fixtures / "github/alerts.json").read_text())
    seen = []
    def handler(req):
        seen.append(json.loads(req.content)["variables"])
        return httpx.Response(200, json=body)
    alerts = make(handler, tmp_path).open_alerts("acme/easton-duels")
    assert seen == [{"owner": "acme", "name": "easton-duels", "after": None}]
    assert alerts[0] == Alert(
        ghsa_id="GHSA-aaaa-bbbb-cccc", severity="high", package="hono", ecosystem="npm",
        vulnerable_range="< 4.6.2", first_patched="4.6.2", summary="Path traversal", description="Long text.",
        permalink="https://github.com/advisories/GHSA-aaaa-bbbb-cccc", manifest_path="server/package.json",
        created_at="2026-09-01T00:00:00Z")
    assert alerts[1].ecosystem == "pypi"
    assert alerts[1].first_patched is None
    assert alerts[1].severity == "moderate"


def test_open_alerts_graphql_error_raises(tmp_path: Path):
    gh = make(lambda req: httpx.Response(200, json={"errors": [{"message": "bad"}]}), tmp_path)
    try:
        gh.open_alerts("o/r")
    except RuntimeError as e:
        assert "bad" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_git_env_askpass_prints_token_without_argv(tmp_path: Path):
    gh = make(lambda req: httpx.Response(200), tmp_path)
    env = gh.git_env()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    helper = Path(env["GIT_ASKPASS"])
    assert helper.exists() and os.access(helper, os.X_OK)
    run_env = {**os.environ, **env}
    user = subprocess.run([str(helper), "Username for 'https://github.com': "], env=run_env, capture_output=True, text=True).stdout
    pw = subprocess.run([str(helper), "Password for 'https://x-access-token@github.com': "], env=run_env, capture_output=True, text=True).stdout
    assert user.strip() == "x-access-token"
    assert pw.strip() == TOKEN
    assert TOKEN not in helper.read_text()


def _alerts_body(nodes):
    return {"data": {"repository": {"vulnerabilityAlerts": {
        "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}


def _good_node():
    return {"createdAt": "2026-09-01T00:00:00Z", "vulnerableManifestPath": "package.json",
            "securityVulnerability": {"severity": "HIGH", "vulnerableVersionRange": "< 4.6.2",
                                      "firstPatchedVersion": {"identifier": "4.6.2"},
                                      "package": {"name": "hono", "ecosystem": "NPM"},
                                      "advisory": {"ghsaId": "GHSA-1", "summary": "S", "description": "D",
                                                   "permalink": "https://github.com/advisories/GHSA-1"}}}


def test_open_alerts_null_connection_is_empty(tmp_path: Path):
    body = {"data": {"repository": {"vulnerabilityAlerts": None}}}
    gh = make(lambda req: httpx.Response(200, json=body), tmp_path)
    assert gh.open_alerts("o/r") == []


def test_open_alerts_skips_null_vulnerability_node(tmp_path: Path):
    body = _alerts_body([{"createdAt": "2026-09-01T00:00:00Z", "vulnerableManifestPath": "p",
                          "securityVulnerability": None}, _good_node()])
    gh = make(lambda req: httpx.Response(200, json=body), tmp_path)
    alerts = gh.open_alerts("o/r")
    assert len(alerts) == 1 and alerts[0].ghsa_id == "GHSA-1"
