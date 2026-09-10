import logging
from pathlib import Path
from typing import Callable

from . import manifests
from .models import Finding
from .versions import gap, newer, parse

log = logging.getLogger("depwatch")
_ORDER = {"major": 0, "minor": 1, "patch": 2}


def _package_url(name: str, ecosystem: str) -> str:
    if ecosystem == "npm":
        return f"https://www.npmjs.com/package/{name}"
    return f"https://pypi.org/project/{name}/"


def collect(repo: str, checkout: Path, registry, github, state, ignored: Callable[[str], bool] = lambda name: False,
            collapse_dev: bool = False) -> list[Finding]:
    lowest: dict[tuple[str, str], str] = {}
    dev_only: dict[tuple[str, str], bool] = {}
    for d in manifests.parse(checkout):
        if d.ecosystem == "docker" or ignored(d.name):
            continue
        key = (d.ecosystem, d.name)
        dev_only[key] = dev_only.get(key, True) and d.kind == "dev"
        if key not in lowest or newer(lowest[key], d.version):
            lowest[key] = d.version
    out: list[Finding] = []
    for (eco, name), current in lowest.items():
        info = registry.latest(name, eco)
        if info is None:
            continue
        severity = gap(current, info.version)
        if severity is None:
            if parse(current) is None or parse(info.version) is None:
                log.debug("%s %s: unparseable version %s or %s", repo, name, current, info.version)
            continue
        if state.release_seen(repo, name, eco, info.version):
            continue
        raw, url = "", _package_url(name, eco)
        if info.github_repo:
            raw, url = github.release_notes(info.github_repo, after=current, upto=info.version)
        out.append(Finding(kind="release", repo=repo, package=name, ecosystem=eco, current=current,
                           target=info.version, severity=severity, source_url=url, raw=raw,
                           dev=collapse_dev and dev_only[(eco, name)]))
    out.sort(key=lambda f: (_ORDER[f.severity], f.package))
    return out
