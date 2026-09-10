from pathlib import Path

from depwatch import manifests
from depwatch.models import Dependency


def by_name(deps):
    return {(d.manifest_path, d.name): d for d in deps}


def test_npm_workspace_resolves_per_workspace(fixtures: Path):
    deps = by_name(manifests.parse(fixtures / "manifests/npm-workspace"))
    assert deps[("package.json", "typescript")] == Dependency("typescript", "npm", "5.6.3", "dev", "package.json")
    assert deps[("server/package.json", "hono")].version == "4.6.1"
    assert deps[("server/package.json", "vitest")].kind == "dev"
    assert deps[("web/package.json", "hono")].version == "4.5.9"
    assert deps[("web/package.json", "react")].version == "19.0.0"


def test_empty_pnpm_lock_is_ignored(fixtures: Path):
    deps = manifests.parse(fixtures / "manifests/npm-workspace")
    assert all(d.version for d in deps if d.ecosystem == "npm")


def test_dockerfile_from_lines(fixtures: Path):
    deps = [d for d in manifests.parse(fixtures / "manifests/npm-workspace") if d.ecosystem == "docker"]
    assert [(d.name, d.version) for d in deps] == [("node", "22-alpine"), ("node", "22-alpine")]
    assert all(d.kind == "base-image" and d.manifest_path == "Dockerfile" for d in deps)


def test_pnpm_lock_strips_peer_suffix(fixtures: Path):
    deps = by_name(manifests.parse(fixtures / "manifests/pnpm"))
    assert deps[("package.json", "next")].version == "16.2.6"
    assert deps[("package.json", "eslint")] == Dependency("eslint", "npm", "9.12.0", "dev", "package.json")


def test_pyproject_without_lock_uses_floor(fixtures: Path):
    deps = by_name(manifests.parse(fixtures / "manifests/pyproject-unlocked"))
    assert deps[("pyproject.toml", "psycopg")] == Dependency("psycopg", "pypi", "3.1", "prod", "pyproject.toml")
    assert deps[("pyproject.toml", "pyyaml")].version == "6"
    assert deps[("pyproject.toml", "pytest")].kind == "dev"


def test_uv_lock_gives_resolved_versions(fixtures: Path):
    deps = by_name(manifests.parse(fixtures / "manifests/uv-locked"))
    assert deps[("pyproject.toml", "httpx")].version == "0.28.1"
    assert deps[("pyproject.toml", "pydantic")].version == "2.13.5"
    assert deps[("pyproject.toml", "pytest")] == Dependency("pytest", "pypi", "9.1.1", "dev", "pyproject.toml")
    assert ("pyproject.toml", "rag") not in deps


def test_requirements_txt(fixtures: Path):
    deps = by_name(manifests.parse(fixtures / "manifests/requirements"))
    assert deps[("requirements.txt", "requests")].version == "2.32.3"
    assert deps[("requirements.txt", "flask")].version == "3.0"
    assert len(deps) == 2


def test_no_manifests_returns_empty(tmp_path: Path):
    assert manifests.parse(tmp_path) == []


def test_node_modules_is_skipped(tmp_path: Path):
    (tmp_path / "node_modules/x").mkdir(parents=True)
    (tmp_path / "node_modules/x/package.json").write_text('{"dependencies": {"a": "1.0.0"}}')
    assert manifests.parse(tmp_path) == []


def test_locked_npm_lock_lists_every_installed_package(fixtures: Path):
    deps = manifests.locked(fixtures / "manifests/npm-workspace")
    assert sorted((d.name, d.version, d.kind, d.manifest_path) for d in deps) == [
        ("hono", "4.5.9", "prod", "package-lock.json"), ("hono", "4.6.1", "prod", "package-lock.json"),
        ("react", "19.0.0", "prod", "package-lock.json"), ("typescript", "5.6.3", "dev", "package-lock.json"),
        ("vitest", "3.2.4", "dev", "package-lock.json")]


def test_locked_pnpm_lock_parses_package_keys(fixtures: Path):
    deps = manifests.locked(fixtures / "manifests/pnpm")
    assert sorted((d.name, d.version) for d in deps) == [("@types/react", "19.0.1"), ("eslint", "9.12.0"), ("next", "16.2.6")]
    assert {(d.ecosystem, d.manifest_path) for d in deps} == {("npm", "pnpm-lock.yaml")}


def test_locked_uv_lock_excludes_the_project_and_editable_members(fixtures: Path):
    deps = manifests.locked(fixtures / "manifests/uv-locked")
    assert sorted((d.name, d.version, d.ecosystem, d.manifest_path) for d in deps) == [
        ("httpx", "0.28.1", "pypi", "uv.lock"), ("pydantic", "2.13.5", "pypi", "uv.lock"), ("pytest", "9.1.1", "pypi", "uv.lock")]


def test_locked_without_lockfiles_is_empty(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"dependencies": {"a": "1.0.0"}}')
    assert manifests.locked(tmp_path) == []
