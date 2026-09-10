from dataclasses import dataclass, field
from typing import Literal

Ecosystem = Literal["npm", "pypi", "docker"]
Severity = Literal["patch", "minor", "major", "low", "moderate", "high", "critical"]


@dataclass(frozen=True)
class Dependency:
    name: str
    ecosystem: Ecosystem
    version: str
    kind: Literal["prod", "dev", "base-image"]
    manifest_path: str


@dataclass
class Finding:
    kind: Literal["release", "landed", "advisory"]
    repo: str
    package: str
    ecosystem: Ecosystem
    current: str | None
    target: str | None
    severity: Severity
    source_url: str
    raw: str
    summary: str | None = None
    risk: Literal["low", "medium", "high"] | None = None
    breakage: str | None = None
    import_sites: list[tuple[str, int, str]] = field(default_factory=list)
    actionable: bool = False
    commit: str | None = None
    commit_date: str | None = None

    @property
    def qualifies_for_tier2(self) -> bool:
        return self.severity in ("major", "high", "critical") and bool(self.import_sites)


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
