import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx

_GH = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s#]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class RegistryInfo:
    version: str
    github_repo: str | None


def _github_repo(*urls: str | None) -> str | None:
    for u in urls:
        if not u:
            continue
        m = _GH.search(u)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


class Registry:
    def __init__(self, client: httpx.Client):
        self.client = client
        self.skipped = 0
        self._memo: dict[tuple[str, str], RegistryInfo | None] = {}

    def latest(self, name: str, ecosystem: str) -> RegistryInfo | None:
        if ecosystem == "docker":
            return None
        key = (ecosystem, name)
        if key not in self._memo:
            self._memo[key] = self._fetch(name, ecosystem)
        return self._memo[key]

    def _fetch(self, name: str, ecosystem: str) -> RegistryInfo | None:
        try:
            if ecosystem == "npm":
                r = self.client.get(f"https://registry.npmjs.org/{quote(name, safe='@')}", timeout=20)
                r.raise_for_status()
                d = r.json()
                repo = d.get("repository")
                url = repo.get("url") if isinstance(repo, dict) else repo
                return RegistryInfo(d["dist-tags"]["latest"], _github_repo(url))
            r = self.client.get(f"https://pypi.org/pypi/{name}/json", timeout=20)
            r.raise_for_status()
            info = r.json()["info"]
            urls = list((info.get("project_urls") or {}).values()) + [info.get("home_page")]
            return RegistryInfo(info["version"], _github_repo(*urls))
        except (httpx.HTTPError, KeyError, ValueError):
            self.skipped += 1
            return None
