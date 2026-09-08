import fnmatch
import json
import os
import re
import tomllib
from pathlib import Path

import yaml

from .models import Dependency
from .versions import floor

MANIFEST_GLOBS = (
    "package.json", "package-lock.json", "pnpm-lock.yaml",
    "pyproject.toml", "uv.lock", "requirements.txt", "requirements-*.txt",
    "Dockerfile", "*.Dockerfile",
)
_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build"}
_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PEP508_SPEC = re.compile(r"[<>=!~]=?.*$")


def _walk(root: Path, names: tuple[str, ...]) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if any(fnmatch.fnmatch(name, n) for n in names):
                out.append(Path(dirpath, name))
    return sorted(out)


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def _nearest(start: Path, root: Path, name: str) -> Path | None:
    d = start
    while True:
        c = d / name
        if c.is_file():
            return c
        if d == root:
            return None
        d = d.parent


def _npm_lock_versions(lock: Path, workspace_rel: str) -> dict[str, str] | None:
    data = json.loads(lock.read_text())
    packages = data.get("packages")
    if not isinstance(packages, dict):
        return None
    out: dict[str, str] = {}
    prefix = f"{workspace_rel}/node_modules/" if workspace_rel else "node_modules/"
    for key, meta in packages.items():
        if key.startswith(prefix) and "/node_modules/" not in key[len(prefix):]:
            out[key[len(prefix):]] = meta.get("version", "")
    if workspace_rel:
        for key, meta in packages.items():
            if key.startswith("node_modules/") and "/node_modules/" not in key[len("node_modules/"):]:
                out.setdefault(key[len("node_modules/"):], meta.get("version", ""))
    return out


def _pnpm_lock_versions(lock: Path, workspace_rel: str) -> dict[str, str] | None:
    data = yaml.safe_load(lock.read_text()) or {}
    importer = (data.get("importers") or {}).get(workspace_rel or ".") or {}
    if not importer:
        return None
    out: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, meta in (importer.get(section) or {}).items():
            version = meta.get("version", "") if isinstance(meta, dict) else str(meta)
            out[name] = version.split("(")[0]
    return out


def _npm(root: Path, manifest: Path) -> list[Dependency]:
    data = json.loads(manifest.read_text())
    resolved: dict[str, str] | None = None
    lock = _nearest(manifest.parent, root, "package-lock.json")
    if lock:
        lock_ws = _rel(root, manifest.parent) if manifest.parent != lock.parent else ""
        resolved = _npm_lock_versions(lock, lock_ws)
    if resolved is None:
        lock = _nearest(manifest.parent, root, "pnpm-lock.yaml")
        if lock:
            lock_ws = _rel(root, manifest.parent) if manifest.parent != lock.parent else ""
            resolved = _pnpm_lock_versions(lock, lock_ws)
    out = []
    for section, kind in (("dependencies", "prod"), ("devDependencies", "dev")):
        for name, spec in (data.get(section) or {}).items():
            version = (resolved or {}).get(name) or floor(str(spec))
            if version:
                out.append(Dependency(name, "npm", version, kind, _rel(root, manifest)))
    return out


def _pypi_name(req: str) -> str | None:
    m = _PEP508_NAME.match(req)
    return re.sub(r"[-_.]+", "-", m.group(1)).lower() if m else None


def _pypi_spec(req: str) -> str:
    m = _PEP508_SPEC.search(req.split(";")[0])
    return m.group(0) if m else ""


def _uv_lock_versions(lock: Path) -> dict[str, str]:
    data = tomllib.loads(lock.read_text())
    return {p["name"].lower(): p["version"] for p in data.get("package", []) if "version" in p}


def _pyproject(root: Path, manifest: Path) -> list[Dependency]:
    data = tomllib.loads(manifest.read_text())
    project = data.get("project", {})
    groups: list[tuple[list[str], str]] = [(project.get("dependencies", []), "prod")]
    for reqs in project.get("optional-dependencies", {}).values():
        groups.append((reqs, "dev"))
    for reqs in data.get("dependency-groups", {}).values():
        groups.append(([r for r in reqs if isinstance(r, str)], "dev"))
    lock = _nearest(manifest.parent, root, "uv.lock")
    resolved = _uv_lock_versions(lock) if lock else {}
    out = []
    for reqs, kind in groups:
        for req in reqs:
            name = _pypi_name(req)
            if not name:
                continue
            version = resolved.get(name) or floor(_pypi_spec(req))
            if version:
                out.append(Dependency(name, "pypi", version, kind, _rel(root, manifest)))
    return out


def _requirements(root: Path, manifest: Path) -> list[Dependency]:
    out = []
    for line in manifest.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        name = _pypi_name(line)
        version = floor(_pypi_spec(line)) if name else None
        if name and version:
            out.append(Dependency(name, "pypi", version, "prod", _rel(root, manifest)))
    return out


def _dockerfile(root: Path, manifest: Path) -> list[Dependency]:
    out, aliases = [], set()
    for line in manifest.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) < 2 or parts[0].upper() != "FROM":
            continue
        image = parts[1]
        if len(parts) >= 4 and parts[2].upper() == "AS":
            aliases.add(parts[3])
        if image in aliases or ":" not in image:
            continue
        name, tag = image.rsplit(":", 1)
        if tag == "latest":
            continue
        out.append(Dependency(name, "docker", tag, "base-image", _rel(root, manifest)))
    return out


def parse(root: Path) -> list[Dependency]:
    out: list[Dependency] = []
    for p in _walk(root, ("package.json",)):
        out.extend(_npm(root, p))
    for p in _walk(root, ("pyproject.toml",)):
        out.extend(_pyproject(root, p))
    for p in _walk(root, ("requirements.txt", "requirements-*.txt")):
        out.extend(_requirements(root, p))
    for p in _walk(root, ("Dockerfile", "*.Dockerfile")):
        out.extend(_dockerfile(root, p))
    return out
