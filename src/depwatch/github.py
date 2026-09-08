import stat
from dataclasses import dataclass
from pathlib import Path

import httpx

from .versions import newer, parse

API = "https://api.github.com"
NOTES_CAP = 4000
_ECOSYSTEM = {"NPM": "npm", "PIP": "pypi"}

ALERTS_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    vulnerabilityAlerts(first: 100, states: OPEN, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        createdAt
        vulnerableManifestPath
        securityVulnerability {
          severity
          vulnerableVersionRange
          firstPatchedVersion { identifier }
          package { name ecosystem }
          advisory { ghsaId summary description permalink }
        }
      }
    }
  }
}
"""

ASKPASS = """#!/bin/sh
case "$1" in
  Username*) echo x-access-token ;;
  *) echo "$GITHUB_TOKEN" ;;
esac
"""


@dataclass(frozen=True)
class Alert:
    ghsa_id: str
    severity: str
    package: str
    ecosystem: str
    vulnerable_range: str
    first_patched: str | None
    summary: str
    description: str
    permalink: str
    manifest_path: str
    created_at: str


class GitHub:
    def __init__(self, client: httpx.Client, token: str, data_dir: Path):
        self.client = client
        self.token = token
        self.data_dir = data_dir

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def release_notes(self, repo: str, after: str, upto: str) -> tuple[str, str]:
        page_url = f"https://github.com/{repo}/releases"
        try:
            r = self.client.get(f"{API}/repos/{repo}/releases", params={"per_page": 100},
                                 headers=self._headers(), timeout=30)
            r.raise_for_status()
            releases = r.json()
        except (httpx.HTTPError, ValueError):
            return "", page_url
        chosen = []
        for rel in releases:
            tag = rel.get("tag_name") or ""
            if parse(tag) is None or not newer(tag, after) or newer(tag, upto):
                continue
            chosen.append(rel)
        chosen.sort(key=lambda rel: parse(rel["tag_name"]), reverse=True)
        if not chosen:
            return "", page_url
        text = "\n\n".join(f"### {rel['tag_name']}\n{(rel.get('body') or '').strip()}" for rel in chosen)
        return text[:NOTES_CAP], chosen[0].get("html_url") or page_url

    def open_alerts(self, repo: str) -> list[Alert]:
        owner, name = repo.split("/")
        out: list[Alert] = []
        after = None
        while True:
            r = self.client.post(f"{API}/graphql", headers=self._headers(), timeout=30,
                                  json={"query": ALERTS_QUERY,
                                        "variables": {"owner": owner, "name": name, "after": after}})
            r.raise_for_status()
            body = r.json()
            if body.get("errors"):
                raise RuntimeError(f"GraphQL error for {repo}: {body['errors'][0].get('message')}")
            conn = body["data"]["repository"]["vulnerabilityAlerts"]
            for node in conn["nodes"]:
                sv = node["securityVulnerability"]
                adv = sv["advisory"]
                eco = sv["package"]["ecosystem"]
                fp = sv.get("firstPatchedVersion")
                out.append(Alert(
                    ghsa_id=adv["ghsaId"], severity=sv["severity"].lower(),
                    package=sv["package"]["name"], ecosystem=_ECOSYSTEM.get(eco, eco.lower()),
                    vulnerable_range=sv["vulnerableVersionRange"],
                    first_patched=fp["identifier"] if fp else None,
                    summary=adv["summary"], description=adv.get("description") or "",
                    permalink=adv["permalink"], manifest_path=node.get("vulnerableManifestPath") or "",
                    created_at=node["createdAt"]))
            if not conn["pageInfo"]["hasNextPage"]:
                return out
            after = conn["pageInfo"]["endCursor"]

    def git_env(self) -> dict[str, str]:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        helper = self.data_dir / "askpass.sh"
        helper.write_text(ASKPASS)
        helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
        return {"GIT_ASKPASS": str(helper), "GIT_TERMINAL_PROMPT": "0", "GITHUB_TOKEN": self.token}
