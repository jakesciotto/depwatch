from pathlib import Path

from depwatch import releases
from depwatch.models import Dependency
from depwatch.registry import RegistryInfo
from depwatch.state import State


class FakeRegistry:
    def __init__(self, table): self.table, self.skipped = table, 0
    def latest(self, name, eco): return self.table.get((eco, name))


class FakeGitHub:
    def __init__(self): self.calls = []
    def release_notes(self, repo, after, upto):
        self.calls.append((repo, after, upto))
        return f"notes {after}->{upto}", f"https://github.com/{repo}/releases/tag/v{upto}"


def write_manifest(root: Path, deps: dict[str, str], sub: str = ""):
    d = root / sub
    d.mkdir(parents=True, exist_ok=True)
    import json
    (d / "package.json").write_text(json.dumps({"dependencies": deps}))


def test_collect_orders_and_annotates(tmp_path: Path):
    write_manifest(tmp_path / "co", {"hono": "4.6.1", "react": "19.0.0", "zod": "3.23.0"})
    reg = FakeRegistry({("npm", "hono"): RegistryInfo("5.0.0", "honojs/hono"),
                        ("npm", "react"): RegistryInfo("19.0.1", None),
                        ("npm", "zod"): RegistryInfo("3.24.0", "colinhacks/zod")})
    gh = FakeGitHub()
    out = releases.collect("o/r", tmp_path / "co", reg, gh, State(tmp_path / "db"))
    assert [(f.package, f.severity, f.current, f.target) for f in out] == [
        ("hono", "major", "4.6.1", "5.0.0"), ("zod", "minor", "3.23.0", "3.24.0"), ("react", "patch", "19.0.0", "19.0.1")]
    assert out[0].raw == "notes 4.6.1->5.0.0"
    assert out[0].source_url == "https://github.com/honojs/hono/releases/tag/v5.0.0"
    assert out[2].raw == "" and out[2].source_url == "https://www.npmjs.com/package/react"
    assert gh.calls == [("honojs/hono", "4.6.1", "5.0.0"), ("colinhacks/zod", "3.23.0", "3.24.0")]
    assert all(f.kind == "release" and f.repo == "o/r" for f in out)


def test_lowest_version_across_workspaces(tmp_path: Path):
    write_manifest(tmp_path / "co", {"hono": "4.6.1"}, "server")
    write_manifest(tmp_path / "co", {"hono": "4.5.0"}, "web")
    reg = FakeRegistry({("npm", "hono"): RegistryInfo("4.6.1", None)})
    out = releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), State(tmp_path / "db"))
    assert [(f.current, f.target, f.severity) for f in out] == [("4.5.0", "4.6.1", "minor")]


def test_up_to_date_and_seen_are_dropped(tmp_path: Path):
    write_manifest(tmp_path / "co", {"a": "1.0.0", "b": "1.0.0"})
    reg = FakeRegistry({("npm", "a"): RegistryInfo("1.0.0", None), ("npm", "b"): RegistryInfo("2.0.0", None)})
    st = State(tmp_path / "db")
    first = releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), st)
    assert [f.package for f in first] == ["b"]
    st.mark_releases(first)
    assert releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), st) == []


def test_pypi_source_url_without_github(tmp_path: Path):
    (tmp_path / "co").mkdir()
    (tmp_path / "co/requirements.txt").write_text("flask==3.0.0\n")
    reg = FakeRegistry({("pypi", "flask"): RegistryInfo("3.1.0", None)})
    out = releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), State(tmp_path / "db"))
    assert out[0].source_url == "https://pypi.org/project/flask/"


def write_full_manifest(root: Path, sub: str = "", **sections):
    d = root / sub
    d.mkdir(parents=True, exist_ok=True)
    import json
    (d / "package.json").write_text(json.dumps(sections))


class CountingRegistry(FakeRegistry):
    def __init__(self, table): super().__init__(table); self.calls = []
    def latest(self, name, eco): self.calls.append(name); return super().latest(name, eco)


def test_ignored_packages_skip_the_registry(tmp_path: Path):
    write_manifest(tmp_path / "co", {"@types/node": "22.0.0", "hono": "4.6.1"})
    reg = CountingRegistry({("npm", "@types/node"): RegistryInfo("22.0.1", None), ("npm", "hono"): RegistryInfo("4.7.0", None)})
    out = releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), State(tmp_path / "db"),
                           ignored=lambda name: name.startswith("@types/"))
    assert [f.package for f in out] == ["hono"] and reg.calls == ["hono"]


def test_dev_in_every_manifest_marks_the_finding_dev(tmp_path: Path):
    write_full_manifest(tmp_path / "co", dependencies={"hono": "4.6.1"}, devDependencies={"vitest": "3.2.0", "eslint": "9.0.0"})
    write_full_manifest(tmp_path / "co", "web", dependencies={"vitest": "3.2.0"})
    reg = FakeRegistry({("npm", "hono"): RegistryInfo("4.7.0", None), ("npm", "vitest"): RegistryInfo("4.0.0", None),
                        ("npm", "eslint"): RegistryInfo("9.1.0", None)})
    out = releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), State(tmp_path / "db"), collapse_dev=True)
    assert {f.package: f.dev for f in out} == {"hono": False, "vitest": False, "eslint": True}


def test_collapse_dev_off_leaves_dev_false(tmp_path: Path):
    write_full_manifest(tmp_path / "co", devDependencies={"eslint": "9.0.0"})
    reg = FakeRegistry({("npm", "eslint"): RegistryInfo("9.1.0", None)})
    out = releases.collect("o/r", tmp_path / "co", reg, FakeGitHub(), State(tmp_path / "db"), collapse_dev=False)
    assert [f.dev for f in out] == [False]
