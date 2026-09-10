import re

import httpx

from .models import Alert, Dependency
from .versions import newer, parse

API = "https://api.osv.dev/v1"
BATCH = 1000
_ECOSYSTEM = {"npm": "npm", "pypi": "PyPI"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _ghsa(rec: dict) -> str | None:
    for candidate in (rec["id"], *rec.get("aliases", [])):
        if candidate.startswith("GHSA-"):
            return candidate
    return None


def _fixed(rec: dict, d: Dependency) -> str | None:
    fixes = [event["fixed"]
             for affected in rec.get("affected", [])
             if _norm(affected["package"]["name"]) == _norm(d.name)
             and affected["package"]["ecosystem"] == _ECOSYSTEM[d.ecosystem]
             for rng in affected.get("ranges", [])
             for event in rng.get("events", []) if "fixed" in event]
    candidates = sorted((v for v in fixes if newer(v, d.version)), key=parse)
    return candidates[0] if candidates else None


class OSV:
    def __init__(self, client: httpx.Client):
        self.client = client
        self._memo: dict[str, dict] = {}

    def alerts(self, deps: list[Dependency]) -> list[Alert]:
        deps = [d for d in deps if d.ecosystem in _ECOSYSTEM]
        out: list[Alert] = []
        for start in range(0, len(deps), BATCH):
            chunk = deps[start:start + BATCH]
            queries = [{"package": {"name": d.name, "ecosystem": _ECOSYSTEM[d.ecosystem]}, "version": d.version}
                       for d in chunk]
            r = self.client.post(f"{API}/querybatch", json={"queries": queries}, timeout=30)
            r.raise_for_status()
            for d, result in zip(chunk, r.json()["results"]):
                ids = [v["id"] for v in result.get("vulns") or []]
                out += [self._alert(d, rec) for rec in self._canonical(ids)]
        return out

    def _canonical(self, ids: list[str]) -> list[dict]:
        """One record per advisory: a GHSA record wins over an alias record for the same GHSA id."""
        chosen: dict[str, dict] = {}
        for vid in ids:
            rec = self._vuln(vid)
            key = _ghsa(rec) or vid
            if key not in chosen or vid == key:
                chosen[key] = rec
        return list(chosen.values())

    def _vuln(self, vid: str) -> dict:
        if vid not in self._memo:
            r = self.client.get(f"{API}/vulns/{vid}", timeout=30)
            r.raise_for_status()
            self._memo[vid] = r.json()
        return self._memo[vid]

    def _alert(self, d: Dependency, rec: dict) -> Alert:
        ghsa = _ghsa(rec)
        permalink = f"https://github.com/advisories/{ghsa}" if ghsa else f"https://osv.dev/vulnerability/{rec['id']}"
        label = (rec.get("database_specific") or {}).get("severity")
        return Alert(ghsa_id=ghsa or rec["id"], severity=label.lower() if label else "moderate",
                     package=d.name, ecosystem=d.ecosystem, vulnerable_range=d.version, first_patched=_fixed(rec, d),
                     summary=rec.get("summary") or "", description=rec.get("details") or "",
                     permalink=permalink, manifest_path=d.manifest_path, created_at=rec.get("published") or "")
